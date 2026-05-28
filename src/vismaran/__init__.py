"""Vismaran — provable right-to-be-forgotten for AI agent memory.

Layered (DDD-influenced) architecture:

- ``vismaran.domain``         — pure models (subject, scope, mode, receipt, provenance, errors)
- ``vismaran.application``    — the orchestrator use case and the ports it depends on
- ``vismaran.infrastructure`` — adapters (Cognee/pgvector/TensorZero), persistence, crypto
- ``vismaran.interfaces``     — the CLI

The names below are the stable public surface; import them from ``vismaran``
directly rather than from their internal modules.
"""

from vismaran._version import __version__
from vismaran.application import Orchestrator
from vismaran.domain import (
    AdapterKind,
    ConfigurationError,
    Mode,
    PartialErasureError,
    PerStoreResult,
    ProvenanceRecord,
    Receipt,
    RecordId,
    Scope,
    SubjectId,
    UntracedSubjectError,
    VismaranError,
)

__all__ = [
    "AdapterKind",
    "ConfigurationError",
    "Mode",
    "Orchestrator",
    "PartialErasureError",
    "PerStoreResult",
    "ProvenanceRecord",
    "Receipt",
    "RecordId",
    "Scope",
    "SubjectId",
    "UntracedSubjectError",
    "VismaranError",
    "__version__",
]
