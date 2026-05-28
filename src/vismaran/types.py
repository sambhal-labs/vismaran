"""Public type vocabulary for Vismaran.

Kept deliberately small in v0 — three enums, three dataclasses, one type alias.
Anything that crosses an adapter boundary uses these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, NewType

SubjectId = NewType("SubjectId", str)
"""Stable subject identifier the operator chose at ingest time.

Conventionally an email or phone number, but Vismaran treats it as an opaque
string. It is hashed before it leaves the local process (see ``Receipt``).
"""

RecordId = NewType("RecordId", str)
"""Framework-native row identifier (e.g., a Cognee node UUID, a pgvector row
UUID, a TensorZero inference UUIDv7)."""


class Scope(StrEnum):
    """Which axis of the data we're erasing along."""

    SUBJECT = "subject"
    DATASET = "dataset"


class Mode(StrEnum):
    """Erasure mode."""

    DRY_RUN = "dry_run"
    COMMIT = "commit"


class AdapterKind(StrEnum):
    """One of the three memory layers."""

    GRAPH = "graph"
    VECTOR = "vector"
    LOG = "log"


@dataclass(frozen=True, slots=True)
class PerStoreResult:
    """What an adapter reports after a preview or erase."""

    adapter_name: str  # e.g., "CogneeGraphAdapter"
    kind: AdapterKind
    counts: dict[str, int]  # e.g., {"nodes_deleted": 14, "edges_deleted": 9}
    method: str  # human-readable description of what the adapter actually did
    succeeded: bool = True
    error: str | None = None  # populated on failure, redacted of PII


@dataclass(frozen=True, slots=True)
class ProvenanceRow:
    """One row in the Vismaran provenance index."""

    subject_id: SubjectId
    framework: str  # "cognee" | "pgvector" | "tensorzero"
    record_id: RecordId
    write_ts: datetime
    tags: dict[str, Any] = field(default_factory=dict)
