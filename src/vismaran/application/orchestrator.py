"""Erasure orchestrator — the application service for a right-to-be-forgotten request.

Responsibilities:

1. Resolve the subject through the provenance store.
2. Fan out to every registered adapter in parallel — :meth:`preview` for a
   dry-run, :meth:`erase` to commit.
3. Collect per-adapter results. On any failure, fail loud
   (``PartialErasureError``) — no provenance purge, **no receipt**.
4. On full success, purge the provenance index and sign a receipt.

The orchestrator is the only component that knows about all three memory
layers; adapters know only their own. It depends on ports
(``vismaran.application.ports``), never on concrete infrastructure — the signer
is injected as a ``ReceiptSigner`` port so the application layer imports no
crypto library.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from vismaran.domain.erasure import Mode, PerStoreResult, Scope
from vismaran.domain.errors import ConfigurationError, PartialErasureError
from vismaran.domain.receipt import Receipt

if TYPE_CHECKING:
    from vismaran.application.ports import ProvenanceStore, ReceiptSigner, StoreAdapter
    from vismaran.domain.identifiers import SubjectId
    from vismaran.domain.provenance import ProvenanceRecord

# A salt below this is too weak to make the hashed subject id brute-force
# resistant if the salt ever leaks (see SPEC.md § Salt confidentiality).
MIN_SALT_BYTES = 16

PROVENANCE_STORE_KEY = "provenance"


class Orchestrator:
    """Coordinate an erasure across registered adapters."""

    def __init__(
        self,
        *,
        provenance: ProvenanceStore,
        adapters: list[StoreAdapter],
        signer: ReceiptSigner,
        subject_salt: bytes,
        operator_id: str,
        clauses: tuple[str, ...] = ("DPDP-2023:S12", "GDPR-Art17"),
    ) -> None:
        if len(subject_salt) < MIN_SALT_BYTES:
            raise ConfigurationError(
                f"subject_salt must be at least {MIN_SALT_BYTES} bytes, got {len(subject_salt)}"
            )
        if not adapters:
            raise ConfigurationError("at least one store adapter is required")
        kinds = [a.kind for a in adapters]
        if len(set(kinds)) != len(kinds):
            raise ConfigurationError(
                f"duplicate adapter kind(s) {kinds}; v0 keys the receipt by layer "
                "and expects one adapter per layer"
            )
        self._provenance = provenance
        self._adapters = adapters
        self._signer = signer
        self._subject_salt = subject_salt
        self._operator_id = operator_id
        self._clauses = clauses

    async def preview(
        self, subject: SubjectId, *, scope: Scope = Scope.SUBJECT
    ) -> list[PerStoreResult]:
        """Dry-run — projected counts per adapter, mutating nothing, signing nothing.

        A store that can't be previewed comes back as a ``succeeded=False`` result
        (exception *type* only, never its message — same subject-redaction as the
        erase path) rather than aborting the whole preview, so the operator still
        sees what the reachable stores would delete.
        """
        provenance = await self._provenance.lookup(subject)
        results = await asyncio.gather(
            *(self._preview_one(a, subject, scope, provenance) for a in self._adapters)
        )
        return list(results)

    async def erase(self, subject: SubjectId, *, scope: Scope = Scope.SUBJECT) -> Receipt:
        """Execute the erasure across all adapters and return a signed receipt.

        Fans out in parallel. If any adapter fails, raises ``PartialErasureError``
        with the per-store status and a correlation id — the provenance index is
        left intact and no receipt is signed. On full success, the provenance
        index is purged and an Ed25519-signed receipt is returned. Idempotent: a
        re-run after success deletes nothing and returns a receipt asserting so.

        Raises:
            PartialErasureError: one or more adapters failed.
        """
        operation_id = str(uuid.uuid4())
        provenance = await self._provenance.lookup(subject)

        results = await asyncio.gather(
            *(self._erase_one(a, subject, scope, provenance) for a in self._adapters)
        )

        failed = [r for r in results if not r.succeeded]
        if failed:
            raise PartialErasureError(
                f"{len(failed)} of {len(results)} adapters failed to erase; no receipt signed",
                per_adapter=list(results),
                operation_id=operation_id,
            )

        purged = await self._provenance.purge(subject)
        receipt = self._build_receipt(subject, results, purged)
        return self._signer.sign(receipt)

    # --- internals ---------------------------------------------------------

    async def _preview_one(
        self,
        adapter: StoreAdapter,
        subject: SubjectId,
        scope: Scope,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        try:
            return await adapter.preview(subject, scope=scope, provenance=provenance)
        except Exception as exc:
            return self._failure_result(adapter, exc, method="preview failed")

    async def _erase_one(
        self,
        adapter: StoreAdapter,
        subject: SubjectId,
        scope: Scope,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        """Run one adapter's commit, turning any failure into a (succeeded=False) result.

        We catch broadly on purpose: one adapter raising must not abort the
        others mid-flight, and the orchestrator reports the *collective* outcome.
        """
        try:
            return await adapter.erase(
                subject, scope=scope, mode=Mode.COMMIT, provenance=provenance
            )
        except Exception as exc:
            return self._failure_result(adapter, exc, method="erase failed")

    @staticmethod
    def _failure_result(adapter: StoreAdapter, exc: Exception, *, method: str) -> PerStoreResult:
        """Per-store failure result. The error is the exception *type* only — never
        its message, which can echo the subject identifier we are erasing."""
        return PerStoreResult(
            adapter_name=adapter.name,
            kind=adapter.kind,
            counts={},
            method=method,
            succeeded=False,
            error=f"{type(exc).__module__}.{type(exc).__qualname__}",
        )

    def _build_receipt(
        self, subject: SubjectId, results: list[PerStoreResult], purged: int
    ) -> Receipt:
        stores: dict[str, dict[str, int | str]] = {}
        for result in results:
            entry: dict[str, int | str] = dict(result.counts)
            entry["method"] = result.method
            stores[result.kind.value] = entry
        stores[PROVENANCE_STORE_KEY] = {
            "rows_purged": purged,
            "method": "provenance index purge",
        }
        return Receipt.build(
            subject_id_hash=self._subject_id_hash(subject),
            salt_hash=self._salt_hash(),
            operator_id=self._operator_id,
            clauses=self._clauses,
            stores=stores,
            issued_at=datetime.now(tz=UTC),
        )

    def _subject_id_hash(self, subject: SubjectId) -> str:
        digest = hashlib.sha256(self._subject_salt + str(subject).encode()).hexdigest()
        return f"sha256:{digest}"

    def _salt_hash(self) -> str:
        return f"sha256:{hashlib.sha256(self._subject_salt).hexdigest()}"
