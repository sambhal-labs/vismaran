"""Erasure result value objects: per-store outcome of a preview or erase."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
