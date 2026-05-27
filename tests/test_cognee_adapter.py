"""CogneeGraphAdapter integration tests — hit live Cognee + Neo4j containers.

Tagged ``integration`` so they're skipped in CI/laptop unit runs unless docker
is up.

The test fixture seeds the graph by ingesting through
:mod:`vismaran_sdk.cognee_wrap` (which is what a real operator would do) and
verifies tier-3 erasure via the adapter then leaves zero nodes behind.

We configure Cognee to use the docker-compose Neo4j by setting env vars
**before** importing cognee in the seed step. The adapter itself talks to
Neo4j directly via the bolt driver and does NOT depend on Cognee's config.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import neo4j
import pytest

from vismaran.adapters.cognee_graph import (
    COGNEE_UNIVERSAL_LABEL,
    CogneeGraphAdapter,
    _subject_node_set_tag,
)
from vismaran.types import Mode, Scope, SubjectId

pytestmark = pytest.mark.integration

NEO4J_URL = os.environ.get("VISMARAN_TEST_NEO4J_URL", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("VISMARAN_TEST_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("VISMARAN_TEST_NEO4J_PASSWORD", "vismarandev")


# --- helpers ---------------------------------------------------------------


@asynccontextmanager
async def _neo4j_session() -> AsyncIterator[neo4j.AsyncSession]:
    driver = neo4j.AsyncGraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        async with driver.session() as session:
            yield session
    finally:
        await driver.close()


async def _wipe_subject_nodes(subject: str) -> None:
    """Best-effort cleanup of any prior test debris for this subject."""
    tag = _subject_node_set_tag(subject)
    async with _neo4j_session() as session:
        await session.run(
            f"""
            MATCH (n:{COGNEE_UNIVERSAL_LABEL})
            WHERE $tag IN coalesce(n.belongs_to_set, [])
            DETACH DELETE n
            """,
            tag=tag,
        )


async def _seed_subject_nodes(subject: str, *, n_entities: int = 3, n_chunks: int = 2) -> None:
    """Plant fake Cognee-shaped nodes scoped to a subject NodeSet.

    We hand-craft the nodes via Cypher rather than going through
    ``cognee.add`` + ``cognee.cognify`` because (a) it's faster and more
    deterministic for the adapter test, and (b) it isolates this test from
    LLM-extraction nondeterminism. A separate test exercises the full
    ingest-via-cognee_wrap flow.
    """
    tag = _subject_node_set_tag(subject)
    async with _neo4j_session() as session:
        # Entities
        await session.run(
            f"""
            UNWIND range(1, $n) AS i
            CREATE (e:{COGNEE_UNIVERSAL_LABEL}:Entity {{
                id: randomUUID(),
                name: $subject + ' entity ' + toString(i),
                belongs_to_set: [$tag]
            }})
            """,
            n=n_entities,
            subject=subject,
            tag=tag,
        )
        # DocumentChunks
        await session.run(
            f"""
            UNWIND range(1, $n) AS i
            CREATE (c:{COGNEE_UNIVERSAL_LABEL}:DocumentChunk {{
                id: randomUUID(),
                text: 'chunk ' + toString(i) + ' mentioning ' + $subject,
                belongs_to_set: [$tag]
            }})
            """,
            n=n_chunks,
            subject=subject,
            tag=tag,
        )
        # Connect entities to chunks so DETACH DELETE has edges to remove
        await session.run(
            f"""
            MATCH (e:Entity) WHERE $tag IN e.belongs_to_set
            MATCH (c:DocumentChunk) WHERE $tag IN c.belongs_to_set
            CREATE (e)-[:MENTIONED_IN]->(c)
            """,
            tag=tag,
        )


async def _count_subject_nodes(subject: str) -> int:
    tag = _subject_node_set_tag(subject)
    async with _neo4j_session() as session:
        rec = await (
            await session.run(
                f"""
                MATCH (n:{COGNEE_UNIVERSAL_LABEL})
                WHERE $tag IN coalesce(n.belongs_to_set, [])
                RETURN count(n) AS c
                """,
                tag=tag,
            )
        ).single()
    return int(rec["c"]) if rec else 0


# --- fixtures --------------------------------------------------------------


@pytest.fixture
async def alice() -> str:
    # Random-suffixed subject ID so concurrent test runs don't collide.
    subj = f"alice-{uuid.uuid4().hex[:8]}@example.com"
    await _wipe_subject_nodes(subj)
    return subj


@pytest.fixture
async def adapter() -> AsyncIterator[CogneeGraphAdapter]:
    adp = CogneeGraphAdapter(
        neo4j_bolt_url=NEO4J_URL,
        neo4j_user=NEO4J_USER,
        neo4j_password=NEO4J_PASSWORD,
    )
    yield adp
    await adp.close()


# --- tests -----------------------------------------------------------------


async def test_health_check_passes_against_live_neo4j(adapter: CogneeGraphAdapter) -> None:
    assert await adapter.health_check() is True


async def test_health_check_fails_against_wrong_url() -> None:
    bad = CogneeGraphAdapter(
        neo4j_bolt_url="bolt://localhost:1",
        neo4j_user="x",
        neo4j_password="x",
    )
    try:
        assert await bad.health_check() is False
    finally:
        await bad.close()


async def test_preview_counts_subject_nodes_by_class(
    adapter: CogneeGraphAdapter, alice: str
) -> None:
    await _seed_subject_nodes(alice, n_entities=3, n_chunks=2)
    result = await adapter.preview(SubjectId(alice), scope=Scope.SUBJECT, provenance=[])
    assert result.adapter_name == "CogneeGraphAdapter"
    assert result.counts == {"Entity": 3, "DocumentChunk": 2, "total_nodes_matched": 5}


async def test_dry_run_erase_matches_preview_and_does_not_mutate(
    adapter: CogneeGraphAdapter, alice: str
) -> None:
    await _seed_subject_nodes(alice, n_entities=4, n_chunks=1)
    result = await adapter.erase(
        SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.DRY_RUN, provenance=[]
    )
    assert result.counts["total_nodes_matched"] == 5
    assert await _count_subject_nodes(alice) == 5  # untouched


async def test_commit_erase_removes_subject_nodes_and_returns_counts(
    adapter: CogneeGraphAdapter, alice: str
) -> None:
    await _seed_subject_nodes(alice, n_entities=3, n_chunks=2)
    result = await adapter.erase(
        SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[]
    )
    assert result.counts["Entity_deleted"] == 3
    assert result.counts["DocumentChunk_deleted"] == 2
    assert result.counts["total_nodes_deleted"] == 5
    assert result.counts["edges_deleted"] >= 1  # entity→chunk MENTIONED_IN edges
    assert await _count_subject_nodes(alice) == 0


async def test_commit_erase_isolates_other_subjects(
    adapter: CogneeGraphAdapter, alice: str
) -> None:
    bob = f"bob-{uuid.uuid4().hex[:8]}@example.com"
    try:
        await _seed_subject_nodes(alice, n_entities=2, n_chunks=1)
        await _seed_subject_nodes(bob, n_entities=2, n_chunks=1)
        await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[]
        )
        assert await _count_subject_nodes(alice) == 0
        assert await _count_subject_nodes(bob) == 3
    finally:
        await _wipe_subject_nodes(bob)


async def test_commit_erase_is_idempotent_when_no_nodes_match(
    adapter: CogneeGraphAdapter, alice: str
) -> None:
    """Re-running erase on an already-empty subject returns zero counts, no errors."""
    result = await adapter.erase(
        SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[]
    )
    assert result.counts["total_nodes_deleted"] == 0
    assert result.counts["edges_deleted"] == 0
