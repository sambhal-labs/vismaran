"""TensorZero SDK wrapper — inject ``vismaran::subject_id`` tag on inference + feedback.

TensorZero exposes ``tags: Map(String, String)`` on both ``/inference`` and
``/feedback`` endpoints. The ``tensorzero::`` prefix is reserved — we use
``vismaran::subject_id`` (see ``vismaran_sdk.tag.TAG_KEY_SUBJECT``).

**Critical:** TensorZero does NOT propagate tags from an inference row to its
derived feedback rows automatically. Every feedback call must be tagged
independently — that's why this module wraps both ``inference()`` and
``feedback()`` and the wrappers' contract is identical: subject_id MUST be in
scope (via ``with_subject``) at every call.

Day-1 spike confirmed this on TensorZero latest (2026-05) — see
``project_adapter_spec.md`` in project memory.

Implementation lands Day 1–4.
"""

from __future__ import annotations

from typing import Any

# Mirror of TensorZeroLogAdapter constants — kept in sync via tests/test_tag.py.
TAG_KEY_SUBJECT = "vismaran::subject_id"
TAG_KEY_TENANT = "vismaran::tenant_id"
TAG_KEY_POLICY = "vismaran::policy_id"


async def inference(
    *,
    function_name: str,
    input: dict[str, Any],  # noqa: A002 — matches TZ's API
    episode_id: str | None = None,
    variant_name: str | None = None,
    extra_tags: dict[str, str] | None = None,
    **tz_kwargs: Any,
) -> Any:
    """Wrap TensorZero's inference call.

    Behavior:
    1. Resolve subject from ``current_subject()``; raise ``UntracedSubjectError``
       if absent and the SDK is configured to fail-loud.
    2. Merge ``{TAG_KEY_SUBJECT: subject_id, ...}`` into ``tags`` and forward.
    3. On success, record a provenance row ``(subject, "tensorzero", inference_id, now)``
       with framework_metadata=``{episode_id, function_name}``.
    """
    raise NotImplementedError("Day 1, then revisited Day 4 for end-to-end test")


async def feedback(
    *,
    metric_name: str,
    value: Any,
    inference_id: str | None = None,
    episode_id: str | None = None,
    extra_tags: dict[str, str] | None = None,
    **tz_kwargs: Any,
) -> Any:
    """Wrap TensorZero's feedback call.

    Tag injection is identical to :func:`inference` — TZ does NOT propagate
    tags from inference to feedback, so the wrapper enforces it here.
    """
    raise NotImplementedError("Day 1, revisited Day 4")
