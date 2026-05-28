"""Orchestrator end-to-end — real pgvector + TensorZero + provenance + signer.

Wires the actual adapters, the Postgres-backed provenance index, and a real
Ed25519 signer against the live docker stack, then erases a subject and proves
the cross-store contract: the receipt verifies offline, both stores are empty,
and the provenance index is purged. The graph layer (Cognee) is covered by its
own adapter integration test (its seeding needs an LLM); here we lock in the
multi-store fan-out + provenance purge + signed-receipt path.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import httpx
import pytest

from vismaran.application import Orchestrator
from vismaran.domain import AdapterKind, SubjectId
from vismaran.infrastructure.adapters import PgvectorVectorAdapter, TensorZeroLogAdapter
from vismaran.infrastructure.adapters.tensorzero_log import TAG_KEY_SUBJECT
from vismaran.infrastructure.crypto import Ed25519ReceiptSigner
from vismaran.infrastructure.persistence import ProvenanceIndex

pytestmark = pytest.mark.integration

PG_DSN = os.environ.get(
    "VISMARAN_TEST_PG_DSN", "postgres://vismaran:vismarandev@localhost:5432/vismaran"
)
CH_URL = os.environ.get("VISMARAN_TEST_CLICKHOUSE_URL", "http://localhost:8123")
CH_USER = os.environ.get("VISMARAN_TEST_CLICKHOUSE_USER", "tensorzero")
CH_PW = os.environ.get("VISMARAN_TEST_CLICKHOUSE_PASSWORD", "vismarandev")
CH_DB = os.environ.get("VISMARAN_TEST_CLICKHOUSE_DB", "tensorzero")
EMBED_DIM = 1536
PG_TABLE = "demo.embeddings"
SALT = b"integration-salt-32-bytes-long!!"


# --- ClickHouse seeding/inspection -----------------------------------------


async def _ch(sql: str, *, sync: bool = False) -> str:
    params = {"database": CH_DB, "user": CH_USER, "password": CH_PW}
    if sync:
        params["mutations_sync"] = "1"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(CH_URL, params=params, content=sql.encode())
        resp.raise_for_status()
        return resp.text


async def _ch_count(table: str, where: str) -> int:
    return int((await _ch(f"SELECT count() FROM {table} WHERE {where}")).strip() or "0")


async def _seed_tz(sid: str) -> str:
    """One tagged ChatInference + its untagged ModelInference. Returns the id."""
    chat_id = str(uuid.uuid4())
    tag = f"map('{TAG_KEY_SUBJECT}', '{sid}')"
    await _ch(
        "INSERT INTO ChatInference (id, function_name, variant_name, episode_id, tags) "
        f"VALUES ('{chat_id}','chat','v0',generateUUIDv4(), {tag})"
    )
    await _ch(
        "INSERT INTO ModelInference (id, inference_id, raw_request, raw_response, "
        "model_name, model_provider_name, input_messages, output) "
        f"VALUES (generateUUIDv4(),'{chat_id}','{sid} secret prompt','resp','m','p','[]','out')"
    )
    return chat_id


async def _tz_remaining(sid: str, chat_id: str) -> int:
    tagq = f"tags['{TAG_KEY_SUBJECT}'] = '{sid}'"
    chat = await _ch_count("ChatInference", tagq)
    model = await _ch_count("ModelInference", f"inference_id = '{chat_id}'")
    return chat + model


async def _tz_cleanup(sid: str, chat_id: str) -> None:
    tagq = f"tags['{TAG_KEY_SUBJECT}']='{sid}'"
    await _ch(f"ALTER TABLE ChatInference DELETE WHERE {tagq}", sync=True)
    await _ch(f"ALTER TABLE ModelInference DELETE WHERE inference_id='{chat_id}'", sync=True)


# --- pgvector seeding/inspection -------------------------------------------


async def _seed_pgvector(index: ProvenanceIndex, sid: str, n: int) -> list[str]:
    """Insert ``n`` embeddings and record a pgvector provenance row for each."""
    vec = "[" + ",".join(["0"] * EMBED_DIM) + "]"
    ids: list[str] = []
    conn = await asyncpg.connect(PG_DSN)
    try:
        for i in range(n):
            row_id = uuid.uuid4()
            await conn.execute(
                f"INSERT INTO {PG_TABLE} (id, source_text, embedding) VALUES ($1,$2,$3::vector)",
                row_id,
                f"{sid} memory {i}",
                vec,
            )
            await index.record(subject_id=sid, framework="pgvector", record_id=str(row_id))
            ids.append(str(row_id))
    finally:
        await conn.close()
    return ids


async def _pg_count(ids: list[str]) -> int:
    if not ids:
        return 0
    conn = await asyncpg.connect(PG_DSN)
    try:
        return await conn.fetchval(  # type: ignore[no-any-return]
            f"SELECT count(*) FROM {PG_TABLE} WHERE id = ANY($1::uuid[])", ids
        )
    finally:
        await conn.close()


async def _pg_cleanup(ids: list[str]) -> None:
    if not ids:
        return
    conn = await asyncpg.connect(PG_DSN)
    try:
        await conn.execute(f"DELETE FROM {PG_TABLE} WHERE id = ANY($1::uuid[])", ids)
    finally:
        await conn.close()


# --- fixtures --------------------------------------------------------------


@pytest.fixture
async def provenance() -> AsyncIterator[ProvenanceIndex]:
    idx = await ProvenanceIndex.from_dsn(PG_DSN)
    yield idx
    await idx.close()


@pytest.fixture
async def adapters() -> AsyncIterator[tuple[PgvectorVectorAdapter, TensorZeroLogAdapter]]:
    pg = PgvectorVectorAdapter(dsn=PG_DSN, table=PG_TABLE, id_column="id")
    tz = TensorZeroLogAdapter(
        clickhouse_url=CH_URL,
        clickhouse_user=CH_USER,
        clickhouse_password=CH_PW,
        clickhouse_database=CH_DB,
    )
    yield pg, tz
    await pg.close()
    await tz.close()


@pytest.fixture
def signer_and_pub(tmp_path: Path) -> tuple[Ed25519ReceiptSigner, Path]:
    priv = tmp_path / "op.key"
    pub = Ed25519ReceiptSigner.generate_keypair(priv)
    return Ed25519ReceiptSigner(signing_key_path=priv), pub


@pytest.fixture
def subject() -> str:
    return f"e2e-{uuid.uuid4().hex[:8]}@example.com"


# --- the end-to-end test ----------------------------------------------------


async def test_erase_across_real_stores_emits_verifiable_receipt(
    provenance: ProvenanceIndex,
    adapters: tuple[PgvectorVectorAdapter, TensorZeroLogAdapter],
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
    subject: str,
) -> None:
    pg, tz = adapters
    signer, pub = signer_and_pub
    pg_ids = await _seed_pgvector(provenance, subject, 4)
    tz_chat = await _seed_tz(subject)
    try:
        orch = Orchestrator(
            provenance=provenance,
            adapters=[pg, tz],
            signer=signer,
            subject_salt=SALT,
            operator_id="e2e-vismaran-deploy",
        )

        # Pre-flight: data is really there, and preview doesn't mutate it.
        assert await _pg_count(pg_ids) == 4
        assert await _tz_remaining(subject, tz_chat) == 2
        assert await provenance.count(subject) == 4
        preview = await orch.preview(SubjectId(subject))
        assert {r.kind for r in preview} == {AdapterKind.VECTOR, AdapterKind.LOG}
        assert await _pg_count(pg_ids) == 4  # preview is read-only

        receipt = await orch.erase(SubjectId(subject))

        # 1. Verifies offline with just the public key.
        assert signer.verify(receipt, public_key_path=pub) is True
        # 2. Records both layers + the provenance purge (the ModelInference
        #    cascade count is the canary — the heaviest-PII table).
        assert receipt.stores["vector"]["embeddings_deleted"] == 4
        assert receipt.stores["log"]["model_inference_rows"] == 1
        assert receipt.stores["log"]["chat_inference_rows"] == 1
        assert receipt.stores["provenance"]["rows_purged"] == 4
        # 3. The raw subject never appears in the receipt.
        assert subject not in receipt.to_json()
        # 4. Both stores are actually empty now.
        assert await _pg_count(pg_ids) == 0
        assert await _tz_remaining(subject, tz_chat) == 0
        # 5. Provenance index purged.
        assert await provenance.count(subject) == 0

        # 6. Idempotent: a second run deletes nothing and still returns a valid
        #    receipt asserting zero rows.
        again = await orch.erase(SubjectId(subject))
        assert signer.verify(again, public_key_path=pub) is True
        assert again.stores["vector"]["embeddings_deleted"] == 0
        assert again.stores["provenance"]["rows_purged"] == 0
    finally:
        await _pg_cleanup(pg_ids)
        await _tz_cleanup(subject, tz_chat)
