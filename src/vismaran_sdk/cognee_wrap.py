"""Cognee SDK wrapper — tag ingest writes with subject_id + record provenance.

Mirrors Cognee's public surface (``cognee.add``, ``cognee.cognify``,
``cognee.search``) but interposes subject-tagging and provenance-recording
around the calls that mutate state. Read paths pass through unmodified.

The wrapper attaches the subject as a Cognee NodeSet tag (``belongs_to_set``
on every node materialized from this ingest) using the prefix
``subject::<subject_id>``. The matching delete path lives in
:mod:`vismaran.infrastructure.adapters.cognee_graph` (tier-3 Cypher scoped to
that tag).

The NodeSet prefix here MUST match
:const:`vismaran.infrastructure.adapters.cognee_graph.SUBJECT_NODE_SET_PREFIX`.
The ``tests/test_tag`` cross-check asserts this at import time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import cognee

from vismaran.domain import UntracedSubjectError
from vismaran_sdk.tag import current_subject

if TYPE_CHECKING:
    from vismaran.application.ports import ProvenanceStore

NODE_SET_SUBJECT_PREFIX = "subject::"
"""Prefix used to encode the subject_id as a Cognee NodeSet tag.

A Cognee NodeSet is a label that groups nodes for cross-dataset queries
(stored as the ``belongs_to_set`` array property on every materialized node).
The tier-3 Cypher in :mod:`vismaran.infrastructure.adapters.cognee_graph`
matches on ``WHERE $tag IN n.belongs_to_set``.
"""

DEFAULT_DATASET = "main_dataset"  # matches cognee.add's default in v1.1.0


def _subject_tag(subject_id: str) -> str:
    return f"{NODE_SET_SUBJECT_PREFIX}{subject_id}"


async def add(
    text: str,
    *,
    dataset_name: str = DEFAULT_DATASET,
    node_set: list[str] | None = None,
    provenance: ProvenanceStore | None = None,
    fail_loud: bool = True,
    **cognee_kwargs: Any,
) -> Any:
    """Wrap ``cognee.add``: tag with subject NodeSet + (optionally) record provenance.

    Behavior:
    1. Resolve subject from :func:`current_subject`. If absent and
       ``fail_loud=True`` (default), raise :class:`UntracedSubjectError` so
       the gap is visible at ingest time — silent fall-throughs are how
       subjects become un-erasable later.
    2. Append ``subject::<subject_id>`` to the ``node_set`` list and forward
       to ``cognee.add(text, dataset_name=..., node_set=...)``.
    3. If a ``ProvenanceStore`` was passed, record one provenance row per
       dataset-id Cognee returns (Cognee may chunk a single add into multiple
       data items).

    Args:
        text: the content to ingest.
        dataset_name: Cognee dataset. Defaults to ``"main_dataset"`` (Cognee's
            own default).
        node_set: additional NodeSet tags to apply. The subject tag is always
            appended.
        provenance: optional :class:`ProvenanceStore`. If supplied, the
            wrapper records a row per Cognee data-id; if None, the caller is
            responsible for recording provenance later.
        fail_loud: when True (default), raise if no subject is in scope.
        **cognee_kwargs: forwarded to ``cognee.add`` unchanged.

    Returns:
        The result of ``cognee.add(...)`` unchanged.

    Raises:
        UntracedSubjectError: when no subject is in scope and ``fail_loud=True``.
    """
    subject_id = current_subject()
    if subject_id is None:
        if fail_loud:
            raise UntracedSubjectError(
                "cognee_wrap.add() called outside any with_subject(...) block. "
                "Either wrap the call site, or pass fail_loud=False to opt out "
                "(and accept that this write will be un-erasable later)."
            )
        return await cognee.add(text, dataset_name=dataset_name, node_set=node_set, **cognee_kwargs)

    tags = list(node_set or [])
    subject_tag = _subject_tag(subject_id)
    if subject_tag not in tags:
        tags.append(subject_tag)

    result = await cognee.add(
        text,
        dataset_name=dataset_name,
        node_set=tags,
        **cognee_kwargs,
    )

    if provenance is not None:
        await _record_cognee_provenance(provenance, subject_id, dataset_name, result)

    return result


async def cognify(**cognee_kwargs: Any) -> Any:
    """Pass-through wrapper for ``cognee.cognify``.

    Cognify materializes already-ingested data into the graph; provenance was
    recorded at :func:`add` time. We keep the wrapper for symmetry and so
    callers can do ``from vismaran_sdk import cognee_wrap as cog`` and use
    ``cog.add`` / ``cog.cognify`` consistently.
    """
    return await cognee.cognify(**cognee_kwargs)


async def _record_cognee_provenance(
    provenance: ProvenanceStore,
    subject_id: str,
    dataset_name: str,
    cognee_add_result: Any,
) -> None:
    """Record one provenance row per Cognee data-id returned by ``cognee.add``.

    Cognee's add() return shape varies by version: in v1.1 it's a list of
    dataset objects each holding ``data`` (list of data items with ``id``).
    We're defensive about the shape since this isn't a stable contract.
    """
    record_ids = _extract_record_ids(cognee_add_result)
    if not record_ids:
        # Fall back to a single row keyed by dataset_name so we at least know
        # something landed for this subject in cognee.
        record_ids = [f"dataset:{dataset_name}"]

    for rid in record_ids:
        await provenance.record(
            subject_id=subject_id,
            framework="cognee",
            record_id=rid,
            tags={"dataset_name": dataset_name},
        )


def _extract_record_ids(cognee_add_result: Any) -> list[str]:
    """Best-effort extraction of data-item IDs from a ``cognee.add`` result."""
    if cognee_add_result is None:
        return []
    # Common shape: list[Dataset(data=list[Data(id=UUID, ...)])]
    if isinstance(cognee_add_result, list):
        ids: list[str] = []
        for entry in cognee_add_result:
            if hasattr(entry, "data") and entry.data:
                for item in entry.data:
                    if hasattr(item, "id"):
                        ids.append(str(item.id))
            elif hasattr(entry, "id"):
                ids.append(str(entry.id))
        return ids
    if hasattr(cognee_add_result, "id"):
        return [str(cognee_add_result.id)]
    return []
