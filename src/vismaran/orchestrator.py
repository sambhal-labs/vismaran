"""Erasure orchestrator — the public entry point for a right-to-be-forgotten request.

Responsibilities:

1. Resolve the subject through the provenance index.
2. Fan out to every registered adapter in parallel — dry-run first, then commit.
3. Collect per-adapter results. On any failure, fail loud (``PartialErasureError``).
4. On full success, sign a receipt and return it.
5. Maintain a local audit log so retries are idempotent.

The orchestrator is the ONLY part of Vismaran that knows about all three
memory layers; adapters know only their own.

Implementation lands Day 4 once all three adapters exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from vismaran.types import Mode, Scope

if TYPE_CHECKING:
    from vismaran.adapters.base import Adapter
    from vismaran.provenance import ProvenanceIndex
    from vismaran.receipt import Receipt
    from vismaran.types import PerStoreResult, SubjectId


class Orchestrator:
    """Coordinate an erasure across registered adapters."""

    def __init__(
        self,
        *,
        provenance: ProvenanceIndex,
        adapters: list[Adapter],
        signing_key_path: Path,
        subject_salt: bytes,
        operator_id: str,
        clauses: tuple[str, ...] = ("DPDP-2023:S12", "GDPR-Art17"),
    ) -> None:
        self._provenance = provenance
        self._adapters = adapters
        self._signing_key_path = signing_key_path
        self._subject_salt = subject_salt
        self._operator_id = operator_id
        self._clauses = clauses

    async def preview(self, subject: SubjectId, *, scope: Scope = Scope.SUBJECT) -> list[PerStoreResult]:
        """Dry-run — return projected counts per adapter without mutating anything."""
        raise NotImplementedError("Day 4")

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope = Scope.SUBJECT,
        mode: Mode = Mode.COMMIT,
    ) -> Receipt:
        """Execute the erasure and return a signed receipt.

        Raises:
            PartialErasureError: any adapter failed. No receipt is signed.
            ConfigurationError: signing key or salt is missing/invalid.
        """
        raise NotImplementedError("Day 4")
