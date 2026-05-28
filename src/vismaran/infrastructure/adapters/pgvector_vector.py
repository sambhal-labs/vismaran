"""PgvectorVectorAdapter — lineage-driven embedding deletion.

Embeddings are opaque — you cannot tell from an embedding whose data it
encodes. So we don't try. Instead, every embedding write goes through
``vismaran_sdk`` and records a provenance row at the moment the row is created.
Erasure becomes: ``DELETE FROM {table} WHERE {id_column} IN (...)`` where the
IDs come from the provenance ledger for this subject (handed in by the
orchestrator).

This is unglamorous but is THE primitive that makes Article 17 tractable for
vector stores. If the operator didn't trace at ingest, there is nothing here to
erase — an empty provenance set is a clean no-op, not an error (the
ingest-time guard against untraced writes lives in ``vismaran_sdk``).

v0 targets the reference schema in ``docker/postgres-init`` where the id column
is a ``UUID`` primary key; deletion matches on the native ``uuid`` type so it
uses the PK index. Non-UUID key types are a future config knob.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import asyncpg

from vismaran.domain.erasure import AdapterKind, Mode, PerStoreResult, Scope
from vismaran.domain.errors import ConfigurationError

if TYPE_CHECKING:
    from vismaran.domain.identifiers import SubjectId
    from vismaran.domain.provenance import ProvenanceRecord

FRAMEWORK = "pgvector"

# table/id_column come from trusted deployment config, but we still validate
# them as plain SQL identifiers before interpolation (defense in depth — they
# are never request/user input, but a typo shouldn't become an injection).
_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _pgvector_record_ids(provenance: list[ProvenanceRecord], subject: SubjectId | str) -> list[str]:
    """Record IDs for this framework AND this subject.

    Filtering on subject as well as framework is defense in depth on a
    destructive path: even if the orchestrator hands us a mis-keyed row, we
    only ever delete rows traced to the subject we were asked to erase.
    """
    return [
        str(r.record_id)
        for r in provenance
        if r.framework == FRAMEWORK and str(r.subject_id) == str(subject)
    ]


class PgvectorVectorAdapter:
    """Erase a subject's embeddings from a pgvector-backed Postgres."""

    name = "PgvectorVectorAdapter"
    kind = AdapterKind.VECTOR

    def __init__(self, *, dsn: str, table: str = "demo.embeddings", id_column: str = "id") -> None:
        """Args:
        dsn: Postgres DSN, e.g. ``"postgresql://vismaran:...@localhost/vismaran"``.
        table: fully-qualified embeddings table, ``schema.name``.
        id_column: PK column on the embeddings table; matches ``record_id``
            in the provenance ledger.
        """
        if not _TABLE_RE.match(table):
            raise ConfigurationError(f"Unsafe table identifier: {table!r}")
        if not _IDENT_RE.match(id_column):
            raise ConfigurationError(f"Unsafe id_column identifier: {id_column!r}")
        self._dsn = dsn
        self._table = table
        self._id_column = id_column
        self._pool: asyncpg.Pool | None = None
        self._pool_lock = asyncio.Lock()

    async def _pool_or_connect(self) -> asyncpg.Pool:
        # Double-checked under a lock: the orchestrator fans adapters out
        # concurrently, so a naive check-then-await-create would let two
        # coroutines each build a pool and orphan one (connection leak).
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)
                    if pool is None:
                        raise ConfigurationError(
                            f"asyncpg.create_pool returned None for dsn={self._dsn!r}"
                        )
                    self._pool = pool
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def health_check(self) -> bool:
        try:
            pool = await self._pool_or_connect()
            async with pool.acquire() as conn:
                return await conn.fetchval("SELECT 1") == 1
        except Exception:
            return False

    async def preview(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        """Count the subject's embedding rows that actually exist (no mutation).

        ``embeddings_matched`` is the count of traced rows still present in the
        table — the honest "this is what an erase would remove" number for the
        receipt, which can be lower than the provenance count if some rows were
        already deleted.
        """
        ids = _pgvector_record_ids(provenance, subject)
        matched = await self._count_existing(ids)
        return PerStoreResult(
            adapter_name=self.name,
            kind=self.kind,
            counts={"embeddings_matched": matched},
            method=f"lineage preview: {len(ids)} traced ids, {matched} present in {self._table}",
        )

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        mode: Mode,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        """Delete the subject's traced embedding rows. Dry-run defers to preview."""
        if mode == Mode.DRY_RUN:
            return await self.preview(subject, scope=scope, provenance=provenance)

        ids = _pgvector_record_ids(provenance, subject)
        deleted = await self._delete_by_ids(ids)
        return PerStoreResult(
            adapter_name=self.name,
            kind=self.kind,
            counts={"embeddings_deleted": deleted},
            method=(
                f"lineage erase: DELETE {deleted} of {len(ids)} traced rows "
                f"from {self._table} by {self._id_column}"
            ),
        )

    # --- internals ---------------------------------------------------------

    async def _count_existing(self, ids: list[str]) -> int:
        if not ids:
            return 0
        pool = await self._pool_or_connect()
        # table/id_column are validated SQL identifiers (see __init__); only the
        # id list is a bound parameter. Match on native uuid so the PK index is used.
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                f"SELECT count(*) FROM {self._table} WHERE {self._id_column} = ANY($1::uuid[])",
                ids,
            )
        return count or 0

    async def _delete_by_ids(self, ids: list[str]) -> int:
        """``DELETE`` the given rows; return the actual rows-removed count.

        The count is parsed from asyncpg's command status (``"DELETE <n>"``) and
        feeds the signed receipt, so a malformed status must surface rather than
        silently report zero — we let the parse raise.
        """
        if not ids:
            return 0
        pool = await self._pool_or_connect()
        # table/id_column are validated SQL identifiers (see __init__); only the
        # id list is a bound parameter. Match on native uuid so the PK index is used.
        async with pool.acquire() as conn:
            status = await conn.execute(
                f"DELETE FROM {self._table} WHERE {self._id_column} = ANY($1::uuid[])",
                ids,
            )
        return int(status.split()[-1])
