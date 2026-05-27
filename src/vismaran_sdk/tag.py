"""Subject tagging — the contextvar that carries subject_id through async writes.

The constants here MUST match those in :mod:`vismaran.adapters.tensorzero_log`.
We keep two copies (one in the adapter module for the deletion path, one here
for the ingest path) so callers never depend on the adapter module just to
ingest. The cross-check is in ``tests/test_tag.py`` to catch drift.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from functools import wraps
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


def current_subject() -> str | None:
    """Return the subject_id active in this async context, if any.

    Returns None outside any :func:`with_subject` block.
    """
    return _subject_var.get()


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
    """
    raise NotImplementedError("Day 1 — straightforward contextvar bind + token reset")
    yield  # pragma: no cover - for type checkers


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
    raise NotImplementedError("Day 1")
    yield  # pragma: no cover


def tag_subject(subject_arg: str = "subject") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: lift a ``subject=`` kwarg of the wrapped function into the contextvar.

    Useful when the agent already accepts a subject argument and you don't
    want to repeat the ``with_subject`` block at every call site::

        @tag_subject()
        async def handle_user_turn(text: str, *, subject: str) -> str: ...

        # `with_subject("alice@...")` happens implicitly inside the call.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError("Day 1")

        return wrapper

    return decorator


# Internal helpers used by the contextmanager implementation when written.
def _bind(
    subject_id: str,
    tenant_id: str | None,
    policy_id: str | None,
) -> tuple[Token[str | None], Token[str | None], Token[str | None]]:
    return (
        _subject_var.set(subject_id),
        _tenant_var.set(tenant_id),
        _policy_var.set(policy_id),
    )


def _unbind(tokens: tuple[Token[str | None], Token[str | None], Token[str | None]]) -> None:
    subject_token, tenant_token, policy_token = tokens
    _subject_var.reset(subject_token)
    _tenant_var.reset(tenant_token)
    _policy_var.reset(policy_token)
