"""Provenance sub-domain: one immutable record of a subject-bearing write."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from vismaran.domain.identifiers import RecordId, SubjectId


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """One row in the Vismaran provenance ledger.

    Records that subject ``subject_id`` caused a write to ``framework`` that
    produced ``record_id`` at ``write_ts``. This is the only thing that makes a
    later opaque-store erasure (e.g., embeddings) possible.
    """

    subject_id: SubjectId
    framework: str  # "cognee" | "pgvector" | "tensorzero"
    record_id: RecordId
    write_ts: datetime
    tags: dict[str, Any] = field(default_factory=dict)
