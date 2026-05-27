"""Provenance index — the Postgres-backed ``(subject_id, framework, record_id, write_ts)`` ledger.

Every write the agent performs against any of the three memory layers leaves
exactly one row here, via the ``vismaran_sdk`` wrappers. Without this index,
Vismaran cannot resolve a subject identifier back to opaque rows (especially
embeddings, where the embedding itself does not encode who it was about).

Schema lives in ``docker/postgres-init/01-pgvector-and-provenance.sql``. This
module is the typed Python API over that schema; the orchestrator and adapters
go through it, never directly to Postgres.

Implementation lands Day 1–2 (records first, then lookup).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    import asyncpg

    from vismaran.types import ProvenanceRow, RecordId, SubjectId


class ProvenanceIndex:
    """Async client for the ``vismaran.provenance`` table.

    Construct via :meth:`from_dsn` (recommended) or by passing a pre-built
    ``asyncpg`` pool to ``__init__``.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def from_dsn(cls, dsn: str) -> Self:
        """Create a pool against the given Postgres DSN and return an index."""
        raise NotImplementedError("Day 1–2 — straightforward asyncpg setup")

    async def close(self) -> None:
        """Close the underlying pool."""
        raise NotImplementedError("Day 1–2")

    # --- write side (called by vismaran_sdk) ---

    async def record(
        self,
        *,
        subject_id: SubjectId,
        framework: str,
        record_id: RecordId,
        write_ts: datetime | None = None,
        tags: dict[str, object] | None = None,
    ) -> None:
        """Append one provenance row.

        Idempotency: ``(subject_id, framework, record_id)`` is the natural
        dedup key; a re-record is a no-op (we never want to double-count).
        """
        raise NotImplementedError("Day 1–2")

    # --- read side (called by the orchestrator + adapters) ---

    async def lookup(self, subject_id: SubjectId) -> list[ProvenanceRow]:
        """All provenance rows for a subject, across all frameworks."""
        raise NotImplementedError("Day 1–2")

    async def lookup_by_framework(
        self, subject_id: SubjectId, framework: str
    ) -> list[ProvenanceRow]:
        """Provenance rows for one subject scoped to one framework."""
        raise NotImplementedError("Day 1–2")

    async def purge(self, subject_id: SubjectId) -> int:
        """Remove every provenance row for a subject.

        Called by the orchestrator AFTER all adapters have confirmed erasure.
        Returns the number of rows removed (for the receipt).
        """
        raise NotImplementedError("Day 1–2")
