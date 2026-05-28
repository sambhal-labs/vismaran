"""TensorZeroLogAdapter — tag-scoped deletion against TensorZero's ClickHouse schema.

Day-1 spike (2026-05-27) findings encoded as module-level constants below.
Full notes in ``project_adapter_spec.md`` in project memory.

Subject scoping. TensorZero exposes ``tags: Map(String, String)`` on both
``/inference`` and ``/feedback``. The ``tensorzero::`` prefix is reserved — we
use ``vismaran::subject_id`` (see ``TAG_KEY_SUBJECT`` below). **No automatic
propagation** from inference to feedback: the SDK wrapper must inject the tag
on every feedback call too.

Cascade gotcha. ``ModelInference`` holds raw provider request/response bodies
(``raw_request``, ``raw_response``, ``system``, ``input_messages``, ``output``)
— this is where the heaviest PII lives — but it has **no tags column**.
Deletion MUST cascade by ``inference_id IN (...)`` joined off the union of
``ChatInference.id`` and ``JsonInference.id``. Forget that join, leak the PII.

Deletion mechanic. ``ALTER TABLE ... DELETE WHERE ...`` heavyweight mutations
(precedent in TZ's own ``dicl_queries.rs:143``). Async, eventually consistent.
Fine for handful-of-subjects/day RTBF volume; capture ``SELECT count()``
pre-mutation for the receipt.

Fast reverse lookup. ``InferenceTag`` (PK ``function_name, key, value`` →
``inference_id``) and ``FeedbackTag`` (PK ``metric_name, key, value`` →
``feedback_id``) materialized views skip full-table scans when subject volumes
are high.

Episode handling. ``episode_id`` is just a column, no ``Episode`` table.
Mixed-subject episodes delete cleanly. Edge case: episode-level
``CommentFeedback`` (``target_type='episode'``) — operator must tag those at
ingest time too; document it in SPEC.

Implementation lands Day 4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vismaran.types import AdapterKind, Mode, Scope

if TYPE_CHECKING:
    from vismaran.types import PerStoreResult, ProvenanceRow, SubjectId

# Tag convention — MUST match ``vismaran_sdk.tag.TAG_KEY_SUBJECT``.
# TensorZero reserves ``tensorzero::`` so we cannot use that prefix.
TAG_KEY_SUBJECT = "vismaran::subject_id"
TAG_KEY_TENANT = "vismaran::tenant_id"
TAG_KEY_POLICY = "vismaran::policy_id"

# ClickHouse tables with a tags column — scoped directly by tag-equality.
TZ_TABLES_TAG_SCOPED = (
    "ChatInference",
    "JsonInference",
    "BooleanMetricFeedback",
    "FloatMetricFeedback",
    "CommentFeedback",
    "DemonstrationFeedback",
)

# ClickHouse table that has NO tags column. Cascade by ``inference_id``
# joined off the union of ChatInference.id and JsonInference.id. This holds raw
# provider request/response bodies; forget this and we leak the data.
TZ_TABLE_CASCADE_BY_INFERENCE_ID = "ModelInference"

# Materialized views for fast tag-keyed reverse lookup.
TZ_TAG_MV_INFERENCE = "InferenceTag"  # PK (function_name, key, value) → inference_id
TZ_TAG_MV_FEEDBACK = "FeedbackTag"  # PK (metric_name, key, value) → feedback_id

# Datapoint tables use is_deleted soft-delete on ReplacingMergeTree;
# prefer flag flip over heavyweight mutation.
TZ_TABLES_SOFT_DELETE = (
    "ChatInferenceDatapoint",
    "JsonInferenceDatapoint",
)


class TensorZeroLogAdapter:
    """Erase a subject's footprint from a TensorZero ClickHouse deployment."""

    name = "TensorZeroLogAdapter"
    kind = AdapterKind.LOG

    def __init__(
        self,
        *,
        clickhouse_url: str,
        clickhouse_user: str,
        clickhouse_password: str,
        clickhouse_database: str = "tensorzero",
    ) -> None:
        """Args:
        clickhouse_url: HTTP endpoint, e.g. ``"http://localhost:8123"``.
        clickhouse_user / clickhouse_password: defaults in our compose
            stack are ``tensorzero / vismarandev``.
        clickhouse_database: TensorZero's database name. Default ``tensorzero``.
        """
        self._url = clickhouse_url
        self._user = clickhouse_user
        self._password = clickhouse_password
        self._db = clickhouse_database

    async def preview(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        provenance: list[ProvenanceRow],
    ) -> PerStoreResult:
        """Pre-query ``SELECT count()`` per table for receipt-grade counts.

        Uses ``InferenceTag`` / ``FeedbackTag`` reverse-lookup MVs when the
        subject's volume is below the heuristic threshold; falls back to a
        direct ``WHERE tags['vismaran::subject_id'] = ...`` scan otherwise.
        """
        raise NotImplementedError("Day 4 — see SPEC.md § Adapters § TensorZero")

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        mode: Mode,
        provenance: list[ProvenanceRow],
    ) -> PerStoreResult:
        """Issue ``ALTER TABLE ... DELETE WHERE ...`` per table.

        Order matters: capture ``inference_id``s from ChatInference + JsonInference
        FIRST, then mutate ModelInference by inference_id, then mutate the
        tag-scoped tables. Otherwise the inference_id list is empty by the time
        we get to ModelInference.
        """
        raise NotImplementedError("Day 4 — see SPEC.md § Adapters § TensorZero")

    async def health_check(self) -> bool:
        raise NotImplementedError("Day 4")
