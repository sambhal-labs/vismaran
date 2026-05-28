"""TensorZeroLogAdapter integration tests — hit live ClickHouse (TensorZero schema).

Erasure here is tag-driven: at ingest, ``vismaran_sdk.tensorzero_wrap`` stamps
``vismaran::subject_id`` into the ``tags`` map on inference + feedback rows.
The adapter deletes every tagged row, and — critically — cascades into
``ModelInference`` (which has **no** tags column but holds the raw provider
request/response, the heaviest PII) by ``inference_id``.

These tests seed the seven tables directly over the ClickHouse HTTP interface
(no LLM needed) and assert the adapter clears every one, including the untagged
ModelInference rows. Deletes use synchronous mutations so assertions are
deterministic.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from vismaran.domain import Mode, Scope, SubjectId
from vismaran.infrastructure.adapters.tensorzero_log import (
    TAG_KEY_SUBJECT,
    TensorZeroLogAdapter,
)

pytestmark = pytest.mark.integration

CH_URL = os.environ.get("VISMARAN_TEST_CLICKHOUSE_URL", "http://localhost:8123")
CH_USER = os.environ.get("VISMARAN_TEST_CLICKHOUSE_USER", "tensorzero")
CH_PW = os.environ.get("VISMARAN_TEST_CLICKHOUSE_PASSWORD", "vismarandev")
CH_DB = os.environ.get("VISMARAN_TEST_CLICKHOUSE_DB", "tensorzero")


# --- raw ClickHouse HTTP helpers (test-side seeding/inspection) -------------


async def _ch(sql: str, *, sync: bool = False) -> str:
    params = {"database": CH_DB, "user": CH_USER, "password": CH_PW}
    if sync:
        params["mutations_sync"] = "1"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(CH_URL, params=params, content=sql.encode())
        resp.raise_for_status()
        return resp.text


async def _count(table: str, where: str) -> int:
    return int((await _ch(f"SELECT count() FROM {table} WHERE {where}")).strip() or "0")


async def _seed_subject(sid: str) -> dict[str, str]:
    """Insert one tagged Chat + Json inference, their (untagged) ModelInference
    rows, and one row in each of the four feedback tables. Returns the ids."""
    chat_id = str(uuid.uuid4())
    json_id = str(uuid.uuid4())
    tag = f"map('{TAG_KEY_SUBJECT}', '{sid}')"

    await _ch(
        "INSERT INTO ChatInference (id, function_name, variant_name, episode_id, tags) "
        f"VALUES ('{chat_id}','chat','v0',generateUUIDv4(), {tag})"
    )
    await _ch(
        "INSERT INTO JsonInference (id, function_name, variant_name, episode_id, tags) "
        f"VALUES ('{json_id}','extract','v0',generateUUIDv4(), {tag})"
    )
    # ModelInference: NO tag column — only the inference_id link. Two rows so we
    # prove the cascade covers both the chat and json sides.
    for inf in (chat_id, json_id):
        await _ch(
            "INSERT INTO ModelInference "
            "(id, inference_id, raw_request, raw_response, model_name, "
            "model_provider_name, input_messages, output) "
            f"VALUES (generateUUIDv4(),'{inf}','{sid} secret prompt','resp','m','p','[]','out')"
        )
    await _ch(
        "INSERT INTO BooleanMetricFeedback (id, target_id, metric_name, value, tags) "
        f"VALUES (generateUUIDv4(),'{chat_id}','thumbs',true, {tag})"
    )
    await _ch(
        "INSERT INTO FloatMetricFeedback (id, target_id, metric_name, value, tags) "
        f"VALUES (generateUUIDv4(),'{chat_id}','score',0.9, {tag})"
    )
    await _ch(
        "INSERT INTO CommentFeedback (id, target_id, target_type, value, tags) "
        f"VALUES (generateUUIDv4(),'{chat_id}','inference','great', {tag})"
    )
    await _ch(
        "INSERT INTO DemonstrationFeedback (id, inference_id, value, tags) "
        f"VALUES (generateUUIDv4(),'{chat_id}','better output', {tag})"
    )
    return {"chat_id": chat_id, "json_id": json_id}


async def _purge_subject(sid: str, ids: dict[str, str]) -> None:
    """Belt-and-suspenders cleanup so a failed assertion can't leave debris."""
    tagq = f"tags['{TAG_KEY_SUBJECT}'] = '{sid}'"
    inf_list = f"'{ids['chat_id']}','{ids['json_id']}'"
    for table in (
        "ChatInference",
        "JsonInference",
        "BooleanMetricFeedback",
        "FloatMetricFeedback",
        "CommentFeedback",
        "DemonstrationFeedback",
    ):
        await _ch(f"ALTER TABLE {table} DELETE WHERE {tagq}", sync=True)
    await _ch(f"ALTER TABLE ModelInference DELETE WHERE inference_id IN ({inf_list})", sync=True)


async def _subject_row_counts(sid: str, ids: dict[str, str]) -> dict[str, int]:
    """How many rows across all seven tables still reference the subject."""
    tagq = f"tags['{TAG_KEY_SUBJECT}'] = '{sid}'"
    inf_list = f"'{ids['chat_id']}','{ids['json_id']}'"
    return {
        "ChatInference": await _count("ChatInference", tagq),
        "JsonInference": await _count("JsonInference", tagq),
        "ModelInference": await _count("ModelInference", f"inference_id IN ({inf_list})"),
        "BooleanMetricFeedback": await _count("BooleanMetricFeedback", tagq),
        "FloatMetricFeedback": await _count("FloatMetricFeedback", tagq),
        "CommentFeedback": await _count("CommentFeedback", tagq),
        "DemonstrationFeedback": await _count("DemonstrationFeedback", tagq),
    }


# --- fixtures --------------------------------------------------------------


@pytest.fixture
async def adapter() -> AsyncIterator[TensorZeroLogAdapter]:
    adp = TensorZeroLogAdapter(
        clickhouse_url=CH_URL,
        clickhouse_user=CH_USER,
        clickhouse_password=CH_PW,
        clickhouse_database=CH_DB,
    )
    yield adp
    await adp.close()


@pytest.fixture
def alice() -> str:
    return f"alice-{uuid.uuid4().hex[:8]}@example.com"


# --- tests -----------------------------------------------------------------


async def test_health_check_passes_against_live_clickhouse(adapter: TensorZeroLogAdapter) -> None:
    assert await adapter.health_check() is True


async def test_health_check_fails_against_bad_url() -> None:
    bad = TensorZeroLogAdapter(
        clickhouse_url="http://localhost:1",
        clickhouse_user="x",
        clickhouse_password="x",
    )
    try:
        assert await bad.health_check() is False
    finally:
        await bad.close()


async def test_preview_counts_every_table_without_mutating(
    adapter: TensorZeroLogAdapter, alice: str
) -> None:
    ids = await _seed_subject(alice)
    try:
        result = await adapter.preview(SubjectId(alice), scope=Scope.SUBJECT, provenance=[])
        assert result.adapter_name == "TensorZeroLogAdapter"
        c = result.counts
        assert c["chat_inference_rows"] == 1
        assert c["json_inference_rows"] == 1
        assert c["model_inference_rows"] == 2  # the cascade target
        assert c["boolean_feedback_rows"] == 1
        assert c["float_feedback_rows"] == 1
        assert c["comment_feedback_rows"] == 1
        assert c["demonstration_feedback_rows"] == 1
        # preview must not mutate
        assert sum((await _subject_row_counts(alice, ids)).values()) == 8
    finally:
        await _purge_subject(alice, ids)


async def test_dry_run_erase_does_not_mutate(adapter: TensorZeroLogAdapter, alice: str) -> None:
    ids = await _seed_subject(alice)
    try:
        await adapter.erase(SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.DRY_RUN, provenance=[])
        assert sum((await _subject_row_counts(alice, ids)).values()) == 8
    finally:
        await _purge_subject(alice, ids)


async def test_commit_erase_clears_all_seven_tables(
    adapter: TensorZeroLogAdapter, alice: str
) -> None:
    ids = await _seed_subject(alice)
    try:
        result = await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[]
        )
        assert result.counts["model_inference_rows"] == 2
        remaining = await _subject_row_counts(alice, ids)
        assert remaining == {
            "ChatInference": 0,
            "JsonInference": 0,
            "ModelInference": 0,
            "BooleanMetricFeedback": 0,
            "FloatMetricFeedback": 0,
            "CommentFeedback": 0,
            "DemonstrationFeedback": 0,
        }
    finally:
        await _purge_subject(alice, ids)


async def test_model_inference_cascade_is_the_canary(
    adapter: TensorZeroLogAdapter, alice: str
) -> None:
    """ModelInference has no subject tag; it MUST still be cleared via inference_id.

    This is the highest-risk bug for the whole project: a tag-only delete would
    leave the raw provider request/response (the heaviest PII) in ClickHouse.
    """
    ids = await _seed_subject(alice)
    try:
        assert (
            await _count(
                "ModelInference", f"inference_id IN ('{ids['chat_id']}','{ids['json_id']}')"
            )
            == 2
        )
        await adapter.erase(SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[])
        assert (
            await _count(
                "ModelInference", f"inference_id IN ('{ids['chat_id']}','{ids['json_id']}')"
            )
            == 0
        )
    finally:
        await _purge_subject(alice, ids)


async def test_commit_erase_isolates_other_subjects(
    adapter: TensorZeroLogAdapter, alice: str
) -> None:
    bob = f"bob-{uuid.uuid4().hex[:8]}@example.com"
    alice_ids = await _seed_subject(alice)
    bob_ids = await _seed_subject(bob)
    try:
        await adapter.erase(SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[])
        assert sum((await _subject_row_counts(alice, alice_ids)).values()) == 0
        assert sum((await _subject_row_counts(bob, bob_ids)).values()) == 8  # bob untouched
    finally:
        await _purge_subject(alice, alice_ids)
        await _purge_subject(bob, bob_ids)


async def test_erase_unknown_subject_is_noop(adapter: TensorZeroLogAdapter, alice: str) -> None:
    result = await adapter.erase(
        SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[]
    )
    assert result.counts["model_inference_rows"] == 0
    assert result.counts["chat_inference_rows"] == 0


async def test_preview_equals_dry_run_counts(adapter: TensorZeroLogAdapter, alice: str) -> None:
    """The port requires DRY_RUN to behave like preview — same counts, no mutation."""
    ids = await _seed_subject(alice)
    try:
        preview = await adapter.preview(SubjectId(alice), scope=Scope.SUBJECT, provenance=[])
        dry = await adapter.erase(
            SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.DRY_RUN, provenance=[]
        )
        assert preview.counts == dry.counts
    finally:
        await _purge_subject(alice, ids)


async def test_cascade_only_follows_tagged_parents(
    adapter: TensorZeroLogAdapter, alice: str
) -> None:
    """Untraced data is left alone — the compliance boundary.

    A ModelInference whose parent ChatInference was never subject-tagged is NOT
    deleted: the cascade resolves only tagged parents. You can't erase what
    wasn't traced; this locks that in as known behavior, not an accidental leak.
    """
    ids = await _seed_subject(alice)
    orphan = str(uuid.uuid4())
    # ChatInference with no subject tag (tags defaults to empty map) + its child.
    await _ch(
        "INSERT INTO ChatInference (id, function_name, variant_name, episode_id) "
        f"VALUES ('{orphan}','chat','v0',generateUUIDv4())"
    )
    await _ch(
        "INSERT INTO ModelInference (id, inference_id, raw_request, raw_response, "
        "model_name, model_provider_name, input_messages, output) "
        f"VALUES (generateUUIDv4(),'{orphan}','untraced','r','m','p','[]','o')"
    )
    try:
        await adapter.erase(SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[])
        assert sum((await _subject_row_counts(alice, ids)).values()) == 0  # alice gone
        # The untagged orphan survives (by design).
        assert await _count("ChatInference", f"id = '{orphan}'") == 1
        assert await _count("ModelInference", f"inference_id = '{orphan}'") == 1
    finally:
        await _purge_subject(alice, ids)
        await _ch(f"ALTER TABLE ChatInference DELETE WHERE id='{orphan}'", sync=True)
        await _ch(f"ALTER TABLE ModelInference DELETE WHERE inference_id='{orphan}'", sync=True)


async def test_erase_fails_loud_with_clickhouse_error_body(
    adapter: TensorZeroLogAdapter, alice: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ClickHouse failure must raise (orchestrator then signs no receipt), and
    the exception must carry ClickHouse's own error text, not a bare status line."""
    from vismaran.infrastructure.adapters import tensorzero_log as mod

    ids = await _seed_subject(alice)
    monkeypatch.setattr(
        mod, "TZ_TAG_SCOPED_TABLES", {**mod.TZ_TAG_SCOPED_TABLES, "NoSuchTable": "nope"}
    )
    try:
        with pytest.raises(httpx.HTTPStatusError, match="ClickHouse"):
            await adapter.erase(
                SubjectId(alice), scope=Scope.SUBJECT, mode=Mode.COMMIT, provenance=[]
            )
    finally:
        await _purge_subject(alice, ids)
