"""vismaran_sdk.tag tests.

Two responsibilities: (1) cross-check that tag-key constants stay in sync
across modules (catches accidental drift between SDK and adapter), and
(2) exercise the contextvar bind / unbind semantics under sync, async, and
nesting.
"""

from __future__ import annotations

import asyncio

import pytest

from vismaran.infrastructure.adapters import tensorzero_log
from vismaran_sdk import tag, tensorzero_wrap

# --- constant drift --------------------------------------------------------


def test_tag_keys_match_across_modules() -> None:
    assert tag.TAG_KEY_SUBJECT == tensorzero_log.TAG_KEY_SUBJECT == tensorzero_wrap.TAG_KEY_SUBJECT
    assert tag.TAG_KEY_TENANT == tensorzero_log.TAG_KEY_TENANT == tensorzero_wrap.TAG_KEY_TENANT
    assert tag.TAG_KEY_POLICY == tensorzero_log.TAG_KEY_POLICY == tensorzero_wrap.TAG_KEY_POLICY


def test_tag_key_uses_vismaran_prefix() -> None:
    """We MUST use the ``vismaran::`` namespace — TensorZero reserves ``tensorzero::``."""
    assert tag.TAG_KEY_SUBJECT.startswith("vismaran::")
    assert not tag.TAG_KEY_SUBJECT.startswith("tensorzero::")


def test_cognee_nodeset_prefix_matches_between_wrap_and_adapter() -> None:
    """SDK ingest tag prefix MUST equal the prefix the adapter scopes deletion to."""
    from vismaran.infrastructure.adapters import cognee_graph
    from vismaran_sdk import cognee_wrap

    assert cognee_wrap.NODE_SET_SUBJECT_PREFIX == cognee_graph.SUBJECT_NODE_SET_PREFIX


# --- current_subject() outside / inside blocks -----------------------------


def test_current_subject_is_none_outside_any_block() -> None:
    assert tag.current_subject() is None
    assert tag.current_tenant() is None
    assert tag.current_policy() is None
    assert tag.current_tags() == {}


def test_sync_with_subject_binds_and_unbinds() -> None:
    with tag.sync_with_subject("alice@example.com", tenant_id="acme", policy_id="rtbf-v1"):
        assert tag.current_subject() == "alice@example.com"
        assert tag.current_tenant() == "acme"
        assert tag.current_policy() == "rtbf-v1"
        assert tag.current_tags() == {
            "vismaran::subject_id": "alice@example.com",
            "vismaran::tenant_id": "acme",
            "vismaran::policy_id": "rtbf-v1",
        }
    assert tag.current_subject() is None
    assert tag.current_tenant() is None
    assert tag.current_policy() is None


def test_sync_with_subject_unbinds_on_exception() -> None:
    with pytest.raises(RuntimeError, match="boom"), tag.sync_with_subject("alice@example.com"):
        assert tag.current_subject() == "alice@example.com"
        raise RuntimeError("boom")
    assert tag.current_subject() is None


async def test_async_with_subject_binds_and_unbinds() -> None:
    async with tag.with_subject("alice@example.com"):
        assert tag.current_subject() == "alice@example.com"
    assert tag.current_subject() is None


async def test_async_with_subject_unbinds_on_exception() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with tag.with_subject("alice@example.com"):
            raise RuntimeError("boom")
    assert tag.current_subject() is None


# --- nesting + concurrency -------------------------------------------------


async def test_nested_with_subject_shadows_outer() -> None:
    async with tag.with_subject("outer@example.com"):
        assert tag.current_subject() == "outer@example.com"
        async with tag.with_subject("inner@example.com"):
            assert tag.current_subject() == "inner@example.com"
        assert tag.current_subject() == "outer@example.com"
    assert tag.current_subject() is None


async def test_subjects_isolated_across_concurrent_tasks() -> None:
    """contextvars semantics: each task gets a private copy of the context."""

    async def fetch_in_block(name: str) -> str:
        async with tag.with_subject(name):
            # Yield so the other task interleaves; if the contextvar were
            # global mutable state this would return the other task's value.
            await asyncio.sleep(0.01)
            return tag.current_subject() or "MISSING"

    results = await asyncio.gather(
        fetch_in_block("alice"),
        fetch_in_block("bob"),
        fetch_in_block("carol"),
    )
    assert results == ["alice", "bob", "carol"]


# --- tag_subject decorator -------------------------------------------------


async def test_tag_subject_decorator_lifts_kwarg_into_contextvar() -> None:
    @tag.tag_subject()
    async def handler(text: str, *, subject: str) -> str | None:
        assert text == "hi"
        return tag.current_subject()

    assert await handler("hi", subject="alice@example.com") == "alice@example.com"
    assert tag.current_subject() is None  # restored after call


async def test_tag_subject_decorator_passthrough_when_subject_missing() -> None:
    @tag.tag_subject()
    async def handler() -> str | None:
        return tag.current_subject()

    # No subject kwarg → no contextvar bind, function still runs.
    assert await handler() is None


def test_tag_subject_decorator_works_on_sync_functions() -> None:
    @tag.tag_subject()
    def handler(*, subject: str) -> str | None:
        return tag.current_subject()

    assert handler(subject="alice@example.com") == "alice@example.com"
    assert tag.current_subject() is None
