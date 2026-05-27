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
3. **Content scope (the wedge).** Cypher fallback against the ``__Node__``
   universal label. Find ``Entity{name CONTAINS $subject}``, walk into
   ``DocumentChunk`` / ``Triplet`` neighborhoods, ``DETACH DELETE`` what's
   subject-only, regex-redact + **re-embed** what's mixed-content. Mirror
   every graph delete with ``vector_engine.delete_data_points(collection,
   [slugs])`` against the ``{NodeType}_{indexed_field}`` collections.

PII strings live in ``Entity.name``, ``DocumentChunk.text``, ``Triplet.text``.
``Entity.id = uuid5(class_name, name)`` so the same subject name across
ingests collapses to a single Entity node — convenient for us, but names can
collide so a confirmation step is needed before destructive tier-3 actions.

Implementation lands Day 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vismaran.types import AdapterKind, Mode, Scope

if TYPE_CHECKING:
    from vismaran.types import PerStoreResult, ProvenanceRow, SubjectId

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


class CogneeGraphAdapter:
    """Erase a subject's footprint from a Cognee deployment."""

    name = "CogneeGraphAdapter"
    kind = AdapterKind.GRAPH

    def __init__(
        self,
        *,
        neo4j_bolt_url: str,
        neo4j_user: str,
        neo4j_password: str,
        re_embed_function: object | None = None,
    ) -> None:
        """Args:
        neo4j_bolt_url: e.g. ``"bolt://localhost:7687"``.
        neo4j_user / neo4j_password: Cognee's default Neo4j credentials in
            our compose stack are ``neo4j / vismarandev``.
        re_embed_function: callable used to re-embed redacted DocumentChunk
            text in tier-3. If None, partial-anonymize is skipped and the
            adapter returns a warning in PerStoreResult.method.
        """
        self._bolt_url = neo4j_bolt_url
        self._neo4j_user = neo4j_user
        self._neo4j_password = neo4j_password
        self._re_embed = re_embed_function

    async def preview(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        provenance: list[ProvenanceRow],
    ) -> PerStoreResult:
        """Pre-query ``MATCH ... RETURN count(n)`` for each PII node class.

        Cognee's own ``forget()`` returns coarse status only (datasets_removed,
        status) — for the signed receipt we need per-node and per-edge counts,
        which only a pre-query gives us.
        """
        raise NotImplementedError("Day 2 — see SPEC.md § Adapters")

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        mode: Mode,
        provenance: list[ProvenanceRow],
    ) -> PerStoreResult:
        raise NotImplementedError("Day 2 — see SPEC.md § Adapters § Cognee tier 1/2/3")

    async def health_check(self) -> bool:
        raise NotImplementedError("Day 2")
