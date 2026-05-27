"""CogneeGraphAdapter — three-tier deletion against Cognee + Neo4j (et al.).

Day-1 spike (2026-05-27, see ``project_adapter_spec.md`` in project memory)
established that Cognee v1.1.0 ships ``cognee.forget(user=, dataset=, data_id=,
everything=)`` covering tenant/dataset/data-item deletion, but has **no** API
for "subject-mentioned-inside-someone-else's-content" — the actual GDPR case.
That tier-3 case is the wedge.

This adapter falls through three tiers in order:

1. **User scope.** If the caller's subject identifier resolves to a Cognee
   user, call ``await cognee.forget(everything=True, user=resolved_user)``.
2. **Dataset scope.** If the caller's subject identifier matches a dataset
   name, call ``await cognee.forget(dataset=subject_id)``.
3. **Content scope (the wedge).** Direct Cypher against Neo4j ``__Node__``
   universal label, scoped to our NodeSet tag ``subject::{subject_id}`` that
   :mod:`vismaran_sdk.cognee_wrap` writes at ingest time. ``DETACH DELETE``
   the matched nodes, return counts.

For v0.1 the adapter implements **tier 3 only** — that's the wedge and the
80/20. Tier 1 and Tier 2 land in v0.2 once we see real callers needing them
(typically dataset-scope deletion at customer-offboarding time).

PII strings live in ``Entity.name``, ``DocumentChunk.text``, ``Triplet.text``.
``Entity.id = uuid5(class_name, name)`` so the same subject name across
ingests collapses to a single Entity node — names can collide, but our
NodeSet-based scoping side-steps that issue entirely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import neo4j

from vismaran.types import AdapterKind, Mode, PerStoreResult, Scope

if TYPE_CHECKING:
    from vismaran.types import ProvenanceRow, SubjectId

# Cognee universal node label — every node in the graph carries this PLUS its
# dynamic class label (Entity, DocumentChunk, Triplet, TextSummary, ...).
COGNEE_UNIVERSAL_LABEL = "__Node__"

# Node classes with PII fields, in priority order for tier-3 scans.
COGNEE_PII_NODE_CLASSES = (
    "Entity",  # canonical extracted subject string in .name
    "DocumentChunk",  # raw ingested text in .text
    "Triplet",  # natural-language subject-predicate-object in .text
)

# Vector collection naming convention: {NodeType}_{indexed_field}.
COGNEE_VECTOR_COLLECTIONS = (
    "Entity_name",
    "DocumentChunk_text",
    "Triplet_text",
)

# NodeSet tag pattern — matches ``vismaran_sdk.cognee_wrap.NODE_SET_SUBJECT_PREFIX``.
SUBJECT_NODE_SET_PREFIX = "subject::"


def _subject_node_set_tag(subject: SubjectId | str) -> str:
    """Compose the NodeSet tag for a subject. Mirror at ingest in cognee_wrap."""
    return f"{SUBJECT_NODE_SET_PREFIX}{subject}"


class CogneeGraphAdapter:
    """Erase a subject's footprint from a Cognee-backed Neo4j graph."""

    name = "CogneeGraphAdapter"
    kind = AdapterKind.GRAPH

    def __init__(
        self,
        *,
        neo4j_bolt_url: str,
        neo4j_user: str,
        neo4j_password: str,
        neo4j_database: str = "neo4j",
    ) -> None:
        self._bolt_url = neo4j_bolt_url
        self._neo4j_user = neo4j_user
        self._neo4j_password = neo4j_password
        self._neo4j_database = neo4j_database
        self._driver: neo4j.AsyncDriver | None = None

    async def _driver_or_connect(self) -> neo4j.AsyncDriver:
        if self._driver is None:
            self._driver = neo4j.AsyncGraphDatabase.driver(
                self._bolt_url,
                auth=(self._neo4j_user, self._neo4j_password),
            )
        return self._driver

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def health_check(self) -> bool:
        try:
            driver = await self._driver_or_connect()
            async with driver.session(database=self._neo4j_database) as session:
                rec = await (await session.run("RETURN 1 AS ok")).single()
            return rec is not None and rec.get("ok") == 1
        except Exception:  # noqa: BLE001 — health check intentionally swallows
            return False

    async def preview(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        provenance: list[ProvenanceRow],
    ) -> PerStoreResult:
        """Pre-query counts by node class without mutating anything.

        Cognee's own ``forget()`` returns coarse status (datasets_removed,
        status) — for the signed receipt we need per-node-class counts, which
        only this pre-query gives us.
        """
        counts = await self._count_by_class(subject)
        total = sum(counts.values())
        return PerStoreResult(
            adapter_name=self.name,
            kind=self.kind,
            counts={**counts, "total_nodes_matched": total},
            method=f"tier-3 preview: NodeSet '{_subject_node_set_tag(subject)}'",
        )

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        mode: Mode,
        provenance: list[ProvenanceRow],
    ) -> PerStoreResult:
        """Tier-3 only in v0.1: Cypher delete of subject-scoped NodeSet members."""
        if mode == Mode.DRY_RUN:
            return await self.preview(subject, scope=scope, provenance=provenance)

        pre = await self._count_by_class(subject)
        nodes_deleted, edges_deleted = await self._delete_by_node_set(subject)
        return PerStoreResult(
            adapter_name=self.name,
            kind=self.kind,
            counts={
                **{f"{k}_deleted": v for k, v in pre.items()},
                "total_nodes_deleted": nodes_deleted,
                "edges_deleted": edges_deleted,
            },
            method=(
                f"tier-3 erase: DETACH DELETE on NodeSet "
                f"'{_subject_node_set_tag(subject)}' "
                f"across {COGNEE_UNIVERSAL_LABEL}"
            ),
        )

    # --- internals ---------------------------------------------------------

    async def _count_by_class(self, subject: SubjectId | str) -> dict[str, int]:
        """Return ``{class_label: count}`` for every node tagged with our subject NodeSet.

        Excludes the universal label so the returned breakdown is by Python
        class (Entity, DocumentChunk, Triplet, ...).
        """
        tag = _subject_node_set_tag(subject)
        driver = await self._driver_or_connect()
        async with driver.session(database=self._neo4j_database) as session:
            cursor = await session.run(
                """
                MATCH (n:__Node__)
                WHERE $tag IN coalesce(n.belongs_to_set, [])
                UNWIND labels(n) AS lbl
                WITH lbl
                WHERE lbl <> $universal
                RETURN lbl AS class, count(*) AS c
                """,
                tag=tag,
                universal=COGNEE_UNIVERSAL_LABEL,
            )
            counts: dict[str, int] = {}
            async for rec in cursor:
                counts[rec["class"]] = rec["c"]
        return counts

    async def _delete_by_node_set(self, subject: SubjectId | str) -> tuple[int, int]:
        """``DETACH DELETE`` every node tagged with the subject NodeSet.

        Returns ``(nodes_deleted, edges_deleted)`` — sourced from Neo4j's own
        ResultSummary counters, so the counts are authoritative regardless of
        what the matched set ended up being.
        """
        tag = _subject_node_set_tag(subject)
        driver = await self._driver_or_connect()
        async with driver.session(database=self._neo4j_database) as session:
            result = await session.run(
                """
                MATCH (n:__Node__)
                WHERE $tag IN coalesce(n.belongs_to_set, [])
                DETACH DELETE n
                """,
                tag=tag,
            )
            summary = await result.consume()
        c = summary.counters
        return c.nodes_deleted, c.relationships_deleted
