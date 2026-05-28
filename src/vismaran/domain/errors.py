"""Exception hierarchy for Vismaran.

Only four exceptions. Exceptions from underlying frameworks (cognee, neo4j,
asyncpg, httpx) are caught by the orchestrator at the adapter boundary and
recorded as the failing adapter's exception *type* — never its message, which
can echo the subject — in that adapter's ``PerStoreResult``. The orchestrator
then raises a single ``PartialErasureError`` describing the collective outcome
(it does not chain the underlying exceptions via ``__cause__``, to keep the
subject out of the traceback).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vismaran.domain.erasure.results import PerStoreResult


class VismaranError(Exception):
    """Base class for everything Vismaran raises."""


class ConfigurationError(VismaranError):
    """Vismaran is misconfigured (missing signing key, missing salt, etc.).

    Raised at orchestrator construction time, not during an erasure.
    """


class UntracedSubjectError(VismaranError):
    """The operator tried to record provenance for an untagged write.

    Raised by ``vismaran_sdk`` when an ingest wrapper is called outside a
    ``with_subject(...)`` block. We fail loud here because silent
    fall-throughs are how subjects become un-erasable.
    """


class PartialErasureError(VismaranError):
    """One or more adapters failed to complete the erasure.

    No receipt is signed and the provenance index is left intact, so a retry can
    resolve the subject again. A wholesale retry is safe — every adapter is
    idempotent, so the adapters that already succeeded report zero on the second
    pass while the previously-failing one completes. ``per_adapter`` is the
    per-store status (each failure carries the exception *type* only); a
    persistent audit log that skips already-succeeded adapters is a post-v0
    optimization. ``operation_id`` correlates the attempt in logs.
    """

    def __init__(
        self,
        message: str,
        per_adapter: list[PerStoreResult],
        operation_id: str,
    ) -> None:
        super().__init__(message)
        self.per_adapter = per_adapter
        self.operation_id = operation_id
