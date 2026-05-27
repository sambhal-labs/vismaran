"""Adapter protocols.

Three runtime-checkable protocols, one per memory layer. New adapter authors
implement the matching protocol; the orchestrator depends only on the protocol,
never on a concrete class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from vismaran.types import AdapterKind, Mode, PerStoreResult, ProvenanceRow, Scope, SubjectId


@runtime_checkable
class Adapter(Protocol):
    """Common surface every Vismaran adapter must expose."""

    name: str
    kind: AdapterKind

    async def preview(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        provenance: list[ProvenanceRow],
    ) -> PerStoreResult:
        """Return projected counts for what an erase would touch.

        MUST NOT mutate state. MUST be fast (regulator-facing UX).
        """
        ...

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        mode: Mode,
        provenance: list[ProvenanceRow],
    ) -> PerStoreResult:
        """Execute the erasure for this adapter's store.

        ``mode=Mode.DRY_RUN`` MUST behave like :meth:`preview`. ``mode=Mode.COMMIT``
        performs the mutation. Adapters raise on failure; orchestrator catches and
        wraps in ``PartialErasureError``.
        """
        ...

    async def health_check(self) -> bool:
        """Return True iff the adapter's downstream is reachable + writable."""
        ...


@runtime_checkable
class GraphAdapter(Adapter, Protocol):
    """Marker protocol for graph-layer adapters (Cognee, Neo4j, Kuzu, ...)."""


@runtime_checkable
class VectorAdapter(Adapter, Protocol):
    """Marker protocol for vector-layer adapters (pgvector, Qdrant, Weaviate, ...)."""


@runtime_checkable
class LogAdapter(Adapter, Protocol):
    """Marker protocol for log-layer adapters (TensorZero, Langfuse, OpenTelemetry, ...)."""
