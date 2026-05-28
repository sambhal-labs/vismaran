"""PgvectorVectorAdapter — lineage-driven embedding deletion.

Embeddings are opaque — you cannot tell from an embedding whose data it
encodes. So we don't try. Instead, every embedding write goes through
``vismaran_sdk`` and records a provenance row at the moment the row is created.
Erasure becomes: ``DELETE FROM {table} WHERE id IN (...)`` where the IDs come
from the provenance index for this subject.

This is unglamorous but is THE primitive that makes Article 17 tractable for
vector stores. If the operator didn't trace at ingest, we can't help.

Implementation lands with the vector-adapter milestone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vismaran.domain.erasure import AdapterKind, Mode, Scope

if TYPE_CHECKING:
    from vismaran.domain.erasure import PerStoreResult
    from vismaran.domain.identifiers import SubjectId
    from vismaran.domain.provenance import ProvenanceRecord


class PgvectorVectorAdapter:
    """Erase a subject's embeddings from a pgvector-backed Postgres."""

    name = "PgvectorVectorAdapter"
    kind = AdapterKind.VECTOR

    def __init__(self, *, dsn: str, table: str = "demo.embeddings", id_column: str = "id") -> None:
        """Args:
        dsn: Postgres DSN, e.g. ``"postgresql://vismaran:...@localhost/vismaran"``.
        table: fully-qualified embeddings table, ``schema.name``.
        id_column: PK column on the embeddings table; matches ``record_id``
            in the provenance index.
        """
        self._dsn = dsn
        self._table = table
        self._id_column = id_column

    async def preview(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        """Return ``{"embeddings_to_delete": len(provenance for pgvector)}``."""
        raise NotImplementedError("Not implemented yet; see SPEC.md (Adapters).")

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        mode: Mode,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        raise NotImplementedError("Not implemented yet; see SPEC.md (Adapters).")

    async def health_check(self) -> bool:
        raise NotImplementedError("Not implemented yet; see SPEC.md (Adapters).")
