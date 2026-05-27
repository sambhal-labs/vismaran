"""Exception hierarchy for Vismaran.

Only four exceptions in v0. The orchestrator and adapters MUST raise one of
these; arbitrary exceptions from underlying frameworks (cognee, neo4j, asyncpg)
should be caught at the adapter boundary and re-raised as ``PartialErasureError``
with the underlying exception attached as ``__cause__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vismaran.types import PerStoreResult


class VismaranError(Exception):
    """Base class for everything Vismaran raises."""


class ConfigurationError(VismaranError):
    """Vismaran is misconfigured (missing signing key, missing salt, etc.).

    Raised at orchestrator construction time, not during an erasure.
    """


class UntracedSubjectError(VismaranError):
    """The operator tried to record provenance for an untagged write.

    Raised by ``vismaran_sdk`` when ``record()`` is called outside a
    ``with_subject(...)`` block. We fail loud here because silent fall-throughs
    are how subjects become un-erasable.
    """


class PartialErasureError(VismaranError):
    """One or more adapters failed to complete the erasure.

    No receipt is signed. The orchestrator marks the operation ``in_progress``
    in the local audit log so a retry is deterministic. ``per_adapter`` is the
    per-store status (succeeded + failed) so the caller can show the user a
    precise picture of what's done and what isn't.
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
