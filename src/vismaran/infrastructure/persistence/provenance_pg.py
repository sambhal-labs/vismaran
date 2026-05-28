"""Provenance index — the Postgres-backed ``(subject_id, framework, record_id, write_ts)`` ledger.

Every write the agent performs against any of the three memory layers leaves
exactly one row here, via the ``vismaran_sdk`` wrappers. Without this index,
Vismaran cannot resolve a subject identifier back to opaque rows (especially
embeddings, where the embedding itself does not encode who it was about).

Schema lives in ``docker/postgres-init/01-pgvector-and-provenance.sql``. This
module is the typed Python API over that schema; the orchestrator and adapters
go through it, never directly to Postgres.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, Self

import asyncpg

from vismaran.domain.identifiers import RecordId, SubjectId
from vismaran.domain.provenance import ProvenanceRecord

if TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_MIN_POOL_SIZE = 1
DEFAULT_MAX_POOL_SIZE = 10


class ProvenanceIndex:
    """Async client for the ``vismaran.provenance`` table.

    Construct via :meth:`from_dsn` (recommended) or by passing a pre-built
    ``asyncpg`` pool to ``__init__``.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def from_dsn(
        cls,
        dsn: str,
        *,
        min_size: int = DEFAULT_MIN_POOL_SIZE,
        max_size: int = DEFAULT_MAX_POOL_SIZE,
    ) -> Self:
        """Create a pool against the given Postgres DSN and return an index."""
        pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            init=_init_connection,
        )
        if pool is None:
            raise RuntimeError(f"asyncpg.create_pool returned None for dsn={dsn!r}")
        return cls(pool)

    async def close(self) -> None:
        """Close the underlying pool."""
        await self._pool.close()

    # --- write side (called by vismaran_sdk) -------------------------------

    async def record(
        self,
        *,
        subject_id: SubjectId | str,
        framework: str,
        record_id: RecordId | str,
        write_ts: datetime | None = None,
        tags: dict[str, Any] | None = None,
    ) -> None:
        """Append one provenance row.

        Idempotent on ``(subject_id, framework, record_id)`` — a re-record is
        a no-op (``ON CONFLICT DO NOTHING``). Existing rows are left alone,
        which is the right behavior: re-recording with new tags shouldn't
        silently change the source-of-truth row.
        """
        tags_json = json.dumps(tags or {})
        async with self._pool.acquire() as conn:
            if write_ts is not None:
                await conn.execute(
                    """
                    INSERT INTO vismaran.provenance
                        (subject_id, framework, record_id, write_ts, tags)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    ON CONFLICT (subject_id, framework, record_id) DO NOTHING
                    """,
                    str(subject_id),
                    framework,
                    str(record_id),
                    write_ts,
                    tags_json,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO vismaran.provenance
                        (subject_id, framework, record_id, tags)
                    VALUES ($1, $2, $3, $4::jsonb)
                    ON CONFLICT (subject_id, framework, record_id) DO NOTHING
                    """,
                    str(subject_id),
                    framework,
                    str(record_id),
                    tags_json,
                )

    async def record_many(self, rows: Iterable[ProvenanceRecord]) -> None:
        """Bulk insert variant for seed scripts.

        Same idempotency contract as :meth:`record`.
        """
        payload = [
            (str(r.subject_id), r.framework, str(r.record_id), r.write_ts, json.dumps(r.tags))
            for r in rows
        ]
        if not payload:
            return
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO vismaran.provenance
                    (subject_id, framework, record_id, write_ts, tags)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (subject_id, framework, record_id) DO NOTHING
                """,
                payload,
            )

    # --- read side (called by the orchestrator + adapters) -----------------

    async def lookup(self, subject_id: SubjectId | str) -> list[ProvenanceRecord]:
        """All provenance rows for a subject, across all frameworks.

        Ordered by ``write_ts`` ascending so a caller can stream them in the
        same order they were written (useful for debugging).
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT subject_id, framework, record_id, write_ts, tags
                FROM vismaran.provenance
                WHERE subject_id = $1
                ORDER BY write_ts ASC
                """,
                str(subject_id),
            )
        return [_row_to_dataclass(r) for r in rows]

    async def lookup_by_framework(
        self,
        subject_id: SubjectId | str,
        framework: str,
    ) -> list[ProvenanceRecord]:
        """Provenance rows for one subject scoped to one framework."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT subject_id, framework, record_id, write_ts, tags
                FROM vismaran.provenance
                WHERE subject_id = $1 AND framework = $2
                ORDER BY write_ts ASC
                """,
                str(subject_id),
                framework,
            )
        return [_row_to_dataclass(r) for r in rows]

    async def count(self, subject_id: SubjectId | str) -> int:
        """Total provenance row count for a subject. Useful for receipt counts."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(  # type: ignore[no-any-return]
                "SELECT count(*) FROM vismaran.provenance WHERE subject_id = $1",
                str(subject_id),
            )

    async def purge(self, subject_id: SubjectId | str) -> int:
        """Remove every provenance row for a subject.

        Called by the orchestrator AFTER all adapters have confirmed erasure.
        Returns the number of rows removed (for the receipt).
        """
        async with self._pool.acquire() as conn:
            tag = await conn.execute(
                "DELETE FROM vismaran.provenance WHERE subject_id = $1",
                str(subject_id),
            )
        # asyncpg.execute returns a status string like "DELETE 7".
        try:
            return int(tag.split()[-1])
        except (ValueError, IndexError):
            return 0


# --- helpers ---------------------------------------------------------------


def _row_to_dataclass(record: asyncpg.Record) -> ProvenanceRecord:
    raw_tags = record["tags"]
    tags = json.loads(raw_tags) if isinstance(raw_tags, str) else (raw_tags or {})
    return ProvenanceRecord(
        subject_id=SubjectId(record["subject_id"]),
        framework=record["framework"],
        record_id=RecordId(record["record_id"]),
        write_ts=record["write_ts"],
        tags=tags,
    )


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Per-connection setup for asyncpg pool.

    Kept tiny: just sets jsonb codec policy. If we ever need search-path
    pinning, do it here.
    """
    # No-op for now; placeholder so future connection-level setup has a home.
    _ = conn
