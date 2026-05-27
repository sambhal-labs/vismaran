"""ProvenanceIndex integration tests.

Hits the live Postgres container brought up by ``make up``. The fixture below
ensures we start each test with an empty ``vismaran.provenance`` table, so
tests don't interfere even if they're re-run individually.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from vismaran.provenance import ProvenanceIndex
from vismaran.types import ProvenanceRow, RecordId, SubjectId

pytestmark = pytest.mark.integration

DEFAULT_DSN = os.environ.get(
    "VISMARAN_TEST_PG_DSN",
    "postgres://vismaran:vismarandev@localhost:5432/vismaran",
)


@pytest.fixture
async def provenance() -> ProvenanceIndex:
    """Fresh ProvenanceIndex against the local Postgres, wiped clean."""
    idx = await ProvenanceIndex.from_dsn(DEFAULT_DSN)
    async with idx._pool.acquire() as conn:  # noqa: SLF001 — test setup
        await conn.execute("TRUNCATE TABLE vismaran.provenance RESTART IDENTITY")
    yield idx
    await idx.close()


async def test_record_then_lookup_roundtrip(provenance: ProvenanceIndex) -> None:
    await provenance.record(
        subject_id="alice@example.com",
        framework="cognee",
        record_id="node-42",
        tags={"node_class": "Entity"},
    )
    rows = await provenance.lookup(SubjectId("alice@example.com"))
    assert len(rows) == 1
    assert rows[0].framework == "cognee"
    assert rows[0].record_id == "node-42"
    assert rows[0].tags == {"node_class": "Entity"}


async def test_record_is_idempotent(provenance: ProvenanceIndex) -> None:
    for _ in range(3):
        await provenance.record(
            subject_id="alice@example.com",
            framework="cognee",
            record_id="node-42",
        )
    assert await provenance.count("alice@example.com") == 1


async def test_record_many_bulk_insert(provenance: ProvenanceIndex) -> None:
    rows = [
        ProvenanceRow(
            subject_id=SubjectId("alice@example.com"),
            framework="pgvector",
            record_id=RecordId(f"emb-{i}"),
            write_ts=datetime.now(tz=UTC),
        )
        for i in range(10)
    ]
    await provenance.record_many(rows)
    assert await provenance.count("alice@example.com") == 10


async def test_lookup_by_framework_filters(provenance: ProvenanceIndex) -> None:
    await provenance.record(subject_id="alice@example.com", framework="cognee", record_id="g-1")
    await provenance.record(subject_id="alice@example.com", framework="pgvector", record_id="v-1")
    await provenance.record(subject_id="alice@example.com", framework="pgvector", record_id="v-2")
    await provenance.record(subject_id="alice@example.com", framework="tensorzero", record_id="t-1")

    cog = await provenance.lookup_by_framework(SubjectId("alice@example.com"), "cognee")
    vec = await provenance.lookup_by_framework(SubjectId("alice@example.com"), "pgvector")
    tz = await provenance.lookup_by_framework(SubjectId("alice@example.com"), "tensorzero")

    assert {r.record_id for r in cog} == {"g-1"}
    assert {r.record_id for r in vec} == {"v-1", "v-2"}
    assert {r.record_id for r in tz} == {"t-1"}


async def test_lookup_returns_only_target_subject(provenance: ProvenanceIndex) -> None:
    await provenance.record(subject_id="alice@example.com", framework="cognee", record_id="g-1")
    await provenance.record(subject_id="bob@example.com", framework="cognee", record_id="g-2")
    rows = await provenance.lookup(SubjectId("alice@example.com"))
    assert {r.record_id for r in rows} == {"g-1"}


async def test_purge_returns_deleted_count(provenance: ProvenanceIndex) -> None:
    for i in range(5):
        await provenance.record(
            subject_id="alice@example.com", framework="pgvector", record_id=f"emb-{i}"
        )
    await provenance.record(subject_id="bob@example.com", framework="pgvector", record_id="emb-99")

    deleted = await provenance.purge("alice@example.com")
    assert deleted == 5
    assert await provenance.count("alice@example.com") == 0
    # Bob's row is untouched.
    assert await provenance.count("bob@example.com") == 1


async def test_purge_returns_zero_when_subject_unknown(provenance: ProvenanceIndex) -> None:
    assert await provenance.purge("nobody@nowhere.invalid") == 0
