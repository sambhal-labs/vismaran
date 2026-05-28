"""Vismaran domain layer.

Pure models with no I/O and no dependency on any other layer. Everything here
is safe to import from anywhere. The common vocabulary is re-exported at this
level so callers can ``from vismaran.domain import SubjectId, Scope, Receipt``
without knowing the sub-module layout.
"""

from vismaran.domain.erasure import AdapterKind, Mode, PerStoreResult, Scope
from vismaran.domain.errors import (
    ConfigurationError,
    PartialErasureError,
    UntracedSubjectError,
    VismaranError,
)
from vismaran.domain.identifiers import RecordId, SubjectId
from vismaran.domain.provenance import ProvenanceRecord
from vismaran.domain.receipt import Receipt

__all__ = [
    "AdapterKind",
    "ConfigurationError",
    "Mode",
    "PartialErasureError",
    "PerStoreResult",
    "ProvenanceRecord",
    "Receipt",
    "RecordId",
    "Scope",
    "SubjectId",
    "UntracedSubjectError",
    "VismaranError",
]
