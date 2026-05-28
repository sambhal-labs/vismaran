"""Subject tagging — the contextvar that carries subject_id through async writes.

The constants here MUST match those in :mod:`vismaran.infrastructure.adapters.tensorzero_log`.
We keep two copies (one in the adapter module for the deletion path, one here
for the ingest path) so callers never depend on the adapter module just to
ingest. The cross-check is in ``tests/test_tag.py`` to catch drift.
"""

from __future__ import annotations

import functools
import inspect
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

# Tag keys (mirror of TensorZeroLogAdapter constants).
# We use the ``vismaran::`` namespace because TensorZero reserves ``tensorzero::``.
TAG_KEY_SUBJECT = "vismaran::subject_id"
TAG_KEY_TENANT = "vismaran::tenant_id"
TAG_KEY_POLICY = "vismaran::policy_id"

_subject_var: ContextVar[str | None] = ContextVar("vismaran_subject", default=None)
_tenant_var: ContextVar[str | None] = ContextVar("vismaran_tenant", default=None)
_policy_var: ContextVar[str | None] = ContextVar("vismaran_policy", default=None)

_BindTokens = tuple[Token[str | None], Token[str | None], Token[str | None]]


def current_subject() -> str | None:
    """Return the subject_id active in this async context, if any.

    Returns None outside any :func:`with_subject` block.
    """
    return _subject_var.get()


def current_tenant() -> str | None:
    """Return the tenant_id active in this async context, if any."""
    return _tenant_var.get()


def current_policy() -> str | None:
    """Return the policy_id active in this async context, if any."""
    return _policy_var.get()


def current_tags() -> dict[str, str]:
    """Return a fresh dict of the active vismaran::* tags.

    Convenience for adapter / wrapper code that needs to merge subject context
    into a request's tag map without three separate ``current_*()`` calls.
    Empty keys are omitted, so the returned dict is safe to merge into
    framework-native tag maps directly.
    """
    out: dict[str, str] = {}
    if (sid := _subject_var.get()) is not None:
        out[TAG_KEY_SUBJECT] = sid
    if (tid := _tenant_var.get()) is not None:
        out[TAG_KEY_TENANT] = tid
    if (pid := _policy_var.get()) is not None:
        out[TAG_KEY_POLICY] = pid
    return out


@asynccontextmanager
async def with_subject(
    subject_id: str,
    *,
    tenant_id: str | None = None,
    policy_id: str | None = None,
) -> AsyncIterator[None]:
    """Async context manager that binds a subject to the current task.

    Every write performed inside this block — through ``cognee_wrap``,
    ``tensorzero_wrap``, or any wrapper that calls :func:`current_subject` —
    will record a provenance row tagged with this subject.

    Usage::

        async with with_subject("alice@example.com"):
            await cognee_add(text="...")
            await tz_inference(function_name="chat", input=...)

    Nested ``with_subject`` blocks are supported; the inner subject shadows
    the outer until the inner block exits. ``contextvars`` semantics — safe
    across ``asyncio.gather`` because each task gets a copy of the context.
    """
    tokens = _bind(subject_id, tenant_id, policy_id)
    try:
        yield
    finally:
        _unbind(tokens)


@contextmanager
def sync_with_subject(
    subject_id: str,
    *,
    tenant_id: str | None = None,
    policy_id: str | None = None,
) -> Iterator[None]:
    """Synchronous flavor of :func:`with_subject` for sync codepaths.

    Less common in agent code, but kept available for ingest scripts.
    """
    tokens = _bind(subject_id, tenant_id, policy_id)
    try:
        yield
    finally:
        _unbind(tokens)


def tag_subject(subject_arg: str = "subject") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: lift a ``subject=`` kwarg of the wrapped function into the contextvar.

    Useful when the agent already accepts a subject argument and you don't
    want to repeat the ``with_subject`` block at every call site::

        @tag_subject()
        async def handle_user_turn(text: str, *, subject: str) -> str: ...

        # `with_subject("alice@...")` happens implicitly inside the call.

    Args:
        subject_arg: the kwarg name on the wrapped function that holds the
            subject identifier. Defaults to ``"subject"``.

    The decorator works on both sync and async callables.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                subject = kwargs.get(subject_arg)
                if subject is None:
                    return await fn(*args, **kwargs)
                async with with_subject(str(subject)):
                    return await fn(*args, **kwargs)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            subject = kwargs.get(subject_arg)
            if subject is None:
                return fn(*args, **kwargs)
            with sync_with_subject(str(subject)):
                return fn(*args, **kwargs)

        return sync_wrapper

    return decorator


# --- internals -------------------------------------------------------------


def _bind(
    subject_id: str,
    tenant_id: str | None,
    policy_id: str | None,
) -> _BindTokens:
    return (
        _subject_var.set(subject_id),
        _tenant_var.set(tenant_id),
        _policy_var.set(policy_id),
    )


def _unbind(tokens: _BindTokens) -> None:
    subject_token, tenant_token, policy_token = tokens
    _subject_var.reset(subject_token)
    _tenant_var.reset(tenant_token)
    _policy_var.reset(policy_token)
