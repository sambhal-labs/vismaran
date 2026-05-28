"""TensorZeroLogAdapter — tag-scoped deletion against TensorZero's ClickHouse schema.

Schema-spike (2026-05-27) findings encoded as module-level constants below.
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
We therefore delete ``ModelInference`` FIRST (while the tagged inference rows
still exist for the subquery to resolve), then the tag-scoped tables.

Deletion mechanic. ``ALTER TABLE ... DELETE WHERE ...`` mutations, run with
``mutations_sync=1`` so the delete is confirmed before we report counts — a
compliance tool should not return "done" on an eventually-consistent promise.
The subject's inference-id set is resolved ONCE at the top of the operation and
reused for both the ModelInference count and its delete, so the cascade does
not depend on the order in which tables are deleted. Counts reflect what this
operation removed (a re-run after a partial failure reports only what that run
removed; the orchestrator signs a receipt only on full success, never partial).

Episode handling. ``episode_id`` is just a column, no ``Episode`` table.
Mixed-subject episodes delete cleanly. Edge case: episode-level
``CommentFeedback`` (``target_type='episode'``) — the operator must tag those
at ingest time too; documented in SPEC.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import httpx

from vismaran.domain.erasure import AdapterKind, Mode, PerStoreResult, Scope

if TYPE_CHECKING:
    from vismaran.domain.identifiers import SubjectId
    from vismaran.domain.provenance import ProvenanceRecord

# Tag convention — MUST match ``vismaran_sdk.tag.TAG_KEY_SUBJECT``.
# TensorZero reserves ``tensorzero::`` so we cannot use that prefix.
TAG_KEY_SUBJECT = "vismaran::subject_id"
TAG_KEY_TENANT = "vismaran::tenant_id"
TAG_KEY_POLICY = "vismaran::policy_id"

# Tag-scoped tables → the receipt count key each contributes.
TZ_TAG_SCOPED_TABLES: dict[str, str] = {
    "ChatInference": "chat_inference_rows",
    "JsonInference": "json_inference_rows",
    "BooleanMetricFeedback": "boolean_feedback_rows",
    "FloatMetricFeedback": "float_feedback_rows",
    "CommentFeedback": "comment_feedback_rows",
    "DemonstrationFeedback": "demonstration_feedback_rows",
}

# ClickHouse table that has NO tags column. Cascade by ``inference_id`` joined
# off the union of ChatInference.id and JsonInference.id. This holds raw
# provider request/response bodies; forget this and we leak the data.
TZ_TABLE_CASCADE_BY_INFERENCE_ID = "ModelInference"
TZ_MODEL_INFERENCE_COUNT_KEY = "model_inference_rows"

# Query resolving the subject's inference ids (chat + json), evaluated once per
# operation. Uses the bound parameter {sid:String}; safe against injection.
_INFERENCE_IDS_QUERY = (
    f"SELECT id FROM ChatInference WHERE tags['{TAG_KEY_SUBJECT}'] = {{sid:String}} "
    f"UNION ALL "
    f"SELECT id FROM JsonInference WHERE tags['{TAG_KEY_SUBJECT}'] = {{sid:String}}"
)


def _tag_predicate() -> str:
    return f"tags['{TAG_KEY_SUBJECT}'] = {{sid:String}}"


def _uuid_in_clause(inference_ids: list[str]) -> str:
    """Build ``inference_id IN ('uuid', ...)`` from a frozen id list.

    Each id is parsed as a UUID before interpolation — they originate from a
    ClickHouse ``SELECT`` so this is belt-and-suspenders against ever putting an
    unvalidated value into SQL. Returns a clause matching nothing when empty.
    """
    if not inference_ids:
        return "1 = 0"  # matches no rows
    quoted = ",".join(f"'{uuid.UUID(i)}'" for i in inference_ids)
    return f"inference_id IN ({quoted})"


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
        self._url = clickhouse_url.rstrip("/")
        self._user = clickhouse_user
        self._password = clickhouse_password
        self._db = clickhouse_database
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def _client_or_connect(self) -> httpx.AsyncClient:
        # Double-checked under a lock — the orchestrator fans adapters out
        # concurrently, so a naive check-then-create would orphan a client.
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _query(self, sql: str, *, sid: str | None = None, sync: bool = False) -> str:
        """POST a statement to the ClickHouse HTTP interface.

        SQL goes in the request body; the subject is bound as the ``sid``
        parameter (never string-interpolated); ``sync`` makes an ``ALTER ...
        DELETE`` mutation block until applied.
        """
        params = {"database": self._db, "user": self._user, "password": self._password}
        if sid is not None:
            params["param_sid"] = sid
        if sync:
            params["mutations_sync"] = "1"
        client = await self._client_or_connect()
        resp = await client.post(self._url, params=params, content=sql.encode())
        if resp.status_code >= 400:
            # ClickHouse returns the actual failure (bad SQL, mutation error,
            # auth) in the body — surface it; the bare status line is useless on
            # a destructive path.
            raise httpx.HTTPStatusError(
                f"ClickHouse {resp.status_code}: {resp.text.strip()}",
                request=resp.request,
                response=resp,
            )
        return resp.text

    async def health_check(self) -> bool:
        try:
            return (await self._query("SELECT 1")).strip() == "1"
        except Exception:
            return False

    async def preview(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        """Count the subject's rows in every table without mutating anything."""
        sid = str(subject)
        inference_ids = await self._subject_inference_ids(sid)
        counts = await self._counts(sid, inference_ids)
        return PerStoreResult(
            adapter_name=self.name,
            kind=self.kind,
            counts=counts,
            method=(
                f"preview: tag '{TAG_KEY_SUBJECT}' across "
                f"{len(TZ_TAG_SCOPED_TABLES)} tables + ModelInference cascade"
            ),
        )

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        mode: Mode,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        """Delete the subject across all seven tables.

        The inference-id set is resolved once, up front, and used for both the
        ModelInference count and its delete — so the cascade is correct
        regardless of table delete order (no dependency on the tagged inference
        rows still existing when ModelInference is deleted).
        """
        if mode == Mode.DRY_RUN:
            return await self.preview(subject, scope=scope, provenance=provenance)

        sid = str(subject)
        inference_ids = await self._subject_inference_ids(sid)
        counts = await self._counts(sid, inference_ids)

        # ModelInference (no tags column) cascaded by the frozen inference-id set.
        if inference_ids:
            await self._query(
                f"ALTER TABLE {TZ_TABLE_CASCADE_BY_INFERENCE_ID} "
                f"DELETE WHERE {_uuid_in_clause(inference_ids)}",
                sync=True,
            )
        # The tag-scoped tables.
        for table in TZ_TAG_SCOPED_TABLES:
            await self._query(
                f"ALTER TABLE {table} DELETE WHERE {_tag_predicate()}",
                sid=sid,
                sync=True,
            )

        return PerStoreResult(
            adapter_name=self.name,
            kind=self.kind,
            counts=counts,
            method=(
                "erase: ALTER TABLE DELETE (mutations_sync=1) — ModelInference "
                "cascaded by frozen inference_id set, then tag-scoped tables"
            ),
        )

    # --- internals ---------------------------------------------------------

    async def _subject_inference_ids(self, sid: str) -> list[str]:
        """Resolve the subject's chat + json inference ids, once per operation."""
        text = await self._query(_INFERENCE_IDS_QUERY, sid=sid)
        return [line.strip() for line in text.splitlines() if line.strip()]

    async def _counts(self, sid: str, inference_ids: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table, key in TZ_TAG_SCOPED_TABLES.items():
            counts[key] = await self._count(
                f"SELECT count() FROM {table} WHERE {_tag_predicate()}", sid=sid
            )
        counts[TZ_MODEL_INFERENCE_COUNT_KEY] = await self._count(
            f"SELECT count() FROM {TZ_TABLE_CASCADE_BY_INFERENCE_ID} "
            f"WHERE {_uuid_in_clause(inference_ids)}"
        )
        return counts

    async def _count(self, sql: str, *, sid: str | None = None) -> int:
        return int((await self._query(sql, sid=sid)).strip() or "0")
