"""Cognee SDK wrapper — tag ingest writes with subject_id + record provenance.

Mirrors Cognee's public surface (``cognee.add``, ``cognee.cognify``,
``cognee.search``) but interposes subject-tagging and provenance-recording
around the calls that mutate state. Read paths pass through unmodified.

Tier alignment with :mod:`vismaran.adapters.cognee_graph`:

- If :func:`vismaran_sdk.tag.current_subject` resolves to a Cognee user email,
  the wrapper passes ``user_id`` through to ``cognee.add`` so tier-1 deletion
  can later use ``cognee.forget(user=...)``.
- Otherwise the wrapper attaches the subject as a node-set tag (``NodeSet``)
  via Cognee's ``add(..., node_set=[f"subject::{subject_id}"])`` so tier-2
  / tier-3 deletion has a starting handle.

Implementation lands Day 1–2.
"""

from __future__ import annotations

from typing import Any

NODE_SET_SUBJECT_PREFIX = "subject::"
"""Prefix used to encode the subject_id as a Cognee node-set tag.

A Cognee NodeSet is just a label that groups nodes for cross-dataset queries
(see Cognee's ``belongs_to_set`` property). We use a prefix so a tier-3
deletion can ``WHERE 'subject::alice@example.com' IN n.belongs_to_set``.
"""


async def add(
    text: str,
    *,
    dataset_name: str = "default",
    **cognee_kwargs: Any,
) -> Any:
    """Wrap ``cognee.add``: tag with subject + record provenance.

    Behavior:
    1. Resolve subject from ``current_subject()``; raise ``UntracedSubjectError``
       if absent and the SDK is configured to fail-loud (default).
    2. Inject ``node_set=[f"subject::{subject_id}"]`` into the call.
    3. Forward to ``cognee.add(text, dataset_name=dataset_name, **kwargs)``.
    4. On success, record a provenance row ``(subject, "cognee", record_id, now)``.
    """
    raise NotImplementedError("Day 1–2 — see SPEC.md § Provenance contract")


async def cognify(**cognee_kwargs: Any) -> Any:
    """Wrap ``cognee.cognify``: pure pass-through, no provenance change.

    Cognify materializes already-ingested data into the graph; provenance was
    recorded at add() time.
    """
    raise NotImplementedError("Day 1–2")
