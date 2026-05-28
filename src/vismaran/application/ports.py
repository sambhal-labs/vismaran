"""Ports — the interfaces the application layer depends on.

These are hexagonal *ports*: Protocols the orchestrator talks to, with concrete
*adapters* (driven side) implemented in the infrastructure layer. The
application layer imports only these Protocols and the domain, never a concrete
infrastructure class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

    from vismaran.domain.erasure import AdapterKind, Mode, PerStoreResult, Scope
    from vismaran.domain.identifiers import RecordId, SubjectId
    from vismaran.domain.provenance import ProvenanceRecord


@runtime_checkable
class StoreAdapter(Protocol):
    """Common surface every memory-layer adapter must expose."""

    name: str
    kind: AdapterKind

    async def preview(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        """Return projected counts for what an erase would touch. MUST NOT mutate."""
        ...

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        mode: Mode,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        """Execute the erasure for this adapter's store.

        ``mode=Mode.DRY_RUN`` MUST behave like :meth:`preview`. ``mode=Mode.COMMIT``
        performs the mutation. Adapters raise on failure; the orchestrator
        catches and wraps in ``PartialErasureError``.
        """
        ...

    async def health_check(self) -> bool:
        """Return True iff the adapter's downstream is reachable and writable."""
        ...


@runtime_checkable
class GraphAdapter(StoreAdapter, Protocol):
    """Marker port for graph-layer adapters (Cognee, Neo4j, Kuzu, ...)."""


@runtime_checkable
class VectorAdapter(StoreAdapter, Protocol):
    """Marker port for vector-layer adapters (pgvector, Qdrant, Weaviate, ...)."""


@runtime_checkable
class LogAdapter(StoreAdapter, Protocol):
    """Marker port for log-layer adapters (TensorZero, Langfuse, OpenTelemetry, ...)."""


@runtime_checkable
class ProvenanceStore(Protocol):
    """Port for the provenance ledger.

    The Postgres implementation (``ProvenanceIndex``) lives in
    ``vismaran.infrastructure.persistence``. The orchestrator and the ingest
    SDK depend on this Protocol, not the concrete class.
    """

    async def record(
        self,
        *,
        subject_id: SubjectId | str,
        framework: str,
        record_id: RecordId | str,
        write_ts: datetime | None = None,
        tags: dict[str, object] | None = None,
    ) -> None: ...

    async def lookup(self, subject_id: SubjectId | str) -> list[ProvenanceRecord]: ...

    async def lookup_by_framework(
        self, subject_id: SubjectId | str, framework: str
    ) -> list[ProvenanceRecord]: ...

    async def count(self, subject_id: SubjectId | str) -> int: ...

    async def purge(self, subject_id: SubjectId | str) -> int: ...
