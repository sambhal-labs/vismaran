"""PgvectorVectorAdapter integration tests — hit live Postgres+pgvector.

Lineage-driven deletion: the adapter is handed the subject's pgvector
``ProvenanceRecord``s (the orchestrator looks them up) and deletes exactly
those embedding rows. These tests seed the ``demo.embeddings`` table directly,
build matching provenance records, and assert the adapter deletes only the
right rows and reports honest counts.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import asyncpg
import pytest

from vismaran.domain import (
    ConfigurationError,
    Mode,
    ProvenanceRecord,
    RecordId,
    Scope,
    SubjectId,
)
from vismaran.infrastructure.adapters.pgvector_vector import PgvectorVectorAdapter

pytestmark = pytest.mark.integration

DSN = os.environ.get(
    "VISMARAN_TEST_PG_DSN", "postgres://vismaran:vismarandev@localhost:5432/vismaran"
)
EMBED_DIM = 1536
TABLE = "demo.embeddings"


def _zero_vec() -> str:
    """A valid pgvector literal of the table's dimensionality."""
    return "[" + ",".join(["0"] * EMBED_DIM) + "]"


@asynccontextmanager
async def _conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(DSN)
    try:
        yield conn
    finally:
        await conn.close()


async def _seed_embeddings(subject: str, n: int) -> list[ProvenanceRecord]:
    """Insert ``n`` embedding rows; return matching pgvector provenance records."""
    records: list[ProvenanceRecord] = []
    async with _conn() as conn:
        for i in range(n):
            row_id = uuid.uuid4()
            await conn.execute(
                f"INSERT INTO {TABLE} (id, source_text, embedding) VALUES ($1, $2, $3::vector)",
                row_id,
                f"{subject} memory {i}",
                _zero_vec(),
            )
            records.append(
                ProvenanceRecord(
                    subject_id=SubjectId(subject),
                    framework="pgvector",
                    record_id=RecordId(str(row_id)),
                    write_ts=datetime.now(tz=UTC),
                )
            )
    return records


async def _count_rows(ids: list[str]) -> int:
    if not ids:
        return 0
    async with _conn() as conn:
        return await conn.fetchval(  # type: ignore[no-any-return]
            f"SELECT count(*) FROM {TABLE} WHERE id = ANY($1::uuid[])",
            ids,
        )


async def _delete_rows(ids: list[str]) -> None:
    if not ids:
        return
    async with _conn() as conn:
        await conn.execute(f"DELETE FROM {TABLE} WHERE id = ANY($1::uuid[])", ids)


def _ids(records: list[ProvenanceRecord]) -> list[str]:
    return [str(r.record_id) for r in records]


# --- fixtures --------------------------------------------------------------


@pytest.fixture
async def adapter() -> AsyncIterator[PgvectorVectorAdapter]:
    adp = PgvectorVectorAdapter(dsn=DSN, table=TABLE, id_column="id")
    yield adp
    await adp.close()


@pytest.fixture
def alice() -> str:
    return f"alice-{uuid.uuid4().hex[:8]}@example.com"


# --- tests -----------------------------------------------------------------


async def test_health_check_passes_against_live_postgres(adapter: PgvectorVectorAdapter) -> None:
    assert await adapter.health_check() is True


async def test_health_check_fails_against_bad_dsn() -> None:
    bad = PgvectorVectorAdapter(dsn="postgres://nobody:nobody@localhost:1/none", table=TABLE)
    try:
        assert await bad.health_check() is False
    finally:
        await bad.close()


async def test_preview_counts_subject_embeddings(
    adapter: PgvectorVectorAdapter, alice: str
) -> None:
    records = await _seed_embeddings(alice, 5)
    try:
        result = await adapter.preview(SubjectId(alice), scope=Scope.SUBJECT, provenance=records)
        assert result.adapter_name == "PgvectorVectorAdapter"
        assert result.counts["embeddings_matched"] == 5
        # preview must not mutate
        assert await _count_rows(_ids(records)) == 5
    finally:
        await _delete_rows(_ids(records))


async def test_dry_run_erase_does_not_mutate(adapter: PgvectorVectorAdapter, alice: str) -> None:
    records = await _seed_embeddings(alice, 3)
    try:
        result = await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.DRY_RUN, provenance=records
        )
        assert result.counts["embeddings_matched"] == 3
        assert await _count_rows(_ids(records)) == 3  # untouched
    finally:
        await _delete_rows(_ids(records))


async def test_commit_erase_deletes_subject_embeddings(
    adapter: PgvectorVectorAdapter, alice: str
) -> None:
    records = await _seed_embeddings(alice, 4)
    ids = _ids(records)
    try:
        result = await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=records
        )
        assert result.counts["embeddings_deleted"] == 4
        assert await _count_rows(ids) == 0
    finally:
        await _delete_rows(ids)


async def test_commit_erase_isolates_other_subjects(
    adapter: PgvectorVectorAdapter, alice: str
) -> None:
    bob = f"bob-{uuid.uuid4().hex[:8]}@example.com"
    alice_records = await _seed_embeddings(alice, 2)
    bob_records = await _seed_embeddings(bob, 3)
    try:
        await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=alice_records
        )
        assert await _count_rows(_ids(alice_records)) == 0
        assert await _count_rows(_ids(bob_records)) == 3  # Bob untouched
    finally:
        await _delete_rows(_ids(alice_records))
        await _delete_rows(_ids(bob_records))


async def test_adapter_ignores_non_pgvector_provenance(
    adapter: PgvectorVectorAdapter, alice: str
) -> None:
    """Defensive: if handed mixed-framework provenance, only act on pgvector rows."""
    records = await _seed_embeddings(alice, 2)
    cognee_noise = ProvenanceRecord(
        subject_id=SubjectId(alice),
        framework="cognee",
        record_id=RecordId(str(uuid.uuid4())),
        write_ts=datetime.now(tz=UTC),
    )
    try:
        result = await adapter.erase(
            SubjectId(alice),
            scope=Scope.SUBJECT,
            mode=Mode.COMMIT,
            provenance=[*records, cognee_noise],
        )
        assert result.counts["embeddings_deleted"] == 2  # not 3
        assert await _count_rows(_ids(records)) == 0
    finally:
        await _delete_rows(_ids(records))


async def test_erase_with_no_pgvector_provenance_is_noop(
    adapter: PgvectorVectorAdapter, alice: str
) -> None:
    """No traced embeddings ⇒ zero deleted, no error (idempotent)."""
    result = await adapter.erase(
        SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[]
    )
    assert result.counts["embeddings_deleted"] == 0


async def test_commit_erase_is_idempotent_on_rerun(
    adapter: PgvectorVectorAdapter, alice: str
) -> None:
    records = await _seed_embeddings(alice, 3)
    ids = _ids(records)
    try:
        first = await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=records
        )
        second = await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=records
        )
        assert first.counts["embeddings_deleted"] == 3
        assert second.counts["embeddings_deleted"] == 0  # already gone
    finally:
        await _delete_rows(ids)


async def test_count_is_honest_after_partial_out_of_band_deletion(
    adapter: PgvectorVectorAdapter, alice: str
) -> None:
    """Receipt honesty: counts reflect rows actually present/removed, not provenance size."""
    records = await _seed_embeddings(alice, 5)
    ids = _ids(records)
    try:
        await _delete_rows(ids[:2])  # 2 vanish out of band; provenance still lists 5

        preview = await adapter.preview(SubjectId(alice), scope=Scope.SUBJECT, provenance=records)
        assert preview.counts["embeddings_matched"] == 3

        result = await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=records
        )
        assert result.counts["embeddings_deleted"] == 3  # not 5
    finally:
        await _delete_rows(ids)


async def test_erase_ignores_other_subjects_provenance(
    adapter: PgvectorVectorAdapter, alice: str
) -> None:
    """Defense in depth: a row traced to a different subject is never deleted."""
    bob = f"bob-{uuid.uuid4().hex[:8]}@example.com"
    bob_records = await _seed_embeddings(bob, 2)
    try:
        # Erase alice, but hand the adapter bob's (same-framework) provenance.
        result = await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=bob_records
        )
        assert result.counts["embeddings_deleted"] == 0
        assert await _count_rows(_ids(bob_records)) == 2  # bob untouched
    finally:
        await _delete_rows(_ids(bob_records))


async def test_malformed_record_id_raises_rather_than_silently_skipping(
    adapter: PgvectorVectorAdapter, alice: str
) -> None:
    """A non-UUID id must surface (fail-loud), never silently match nothing."""
    bad = ProvenanceRecord(
        subject_id=SubjectId(alice),
        framework="pgvector",
        record_id=RecordId("not-a-uuid"),
        write_ts=datetime.now(tz=UTC),
    )
    with pytest.raises(asyncpg.PostgresError, match=r"uuid"):
        await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[bad]
        )


async def test_pool_is_created_once_under_concurrency(adapter: PgvectorVectorAdapter) -> None:
    """The double-checked lock must not let concurrent calls orphan a pool."""
    await asyncio.gather(*(adapter.health_check() for _ in range(8)))
    assert adapter._pool is not None
    pool_id = id(adapter._pool)
    await asyncio.gather(*(adapter.health_check() for _ in range(8)))
    assert id(adapter._pool) == pool_id


def test_construction_rejects_unsafe_table_identifier() -> None:
    with pytest.raises(ConfigurationError, match="table identifier"):
        PgvectorVectorAdapter(dsn=DSN, table="embeddings; DROP TABLE x")


def test_construction_rejects_unsafe_id_column() -> None:
    with pytest.raises(ConfigurationError, match="id_column identifier"):
        PgvectorVectorAdapter(dsn=DSN, table=TABLE, id_column="id; --")
