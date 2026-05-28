"""Receipt sub-domain: the signed deletion receipt value object.

A receipt holds **metadata only** — a salted hash of the subject identifier,
per-store counts, the operator ID, the clause(s) the action satisfies, and a
timestamp. The raw subject identifier never appears in a receipt; that would
defeat the point of erasing it.

This module is pure domain: the Receipt value object and its canonical
serialization. The Ed25519 signing/verification is an infrastructure concern
and lives in ``vismaran.infrastructure.crypto`` — a signer operates *on* a
Receipt; the Receipt itself imports no crypto library.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Self

VERSION = "vismaran/v0.1"


@dataclass(frozen=True, slots=True)
class Receipt:
    """Canonical deletion receipt (metadata only; immutable).

    Construct via :meth:`build`, hand to an infrastructure signer to populate
    ``manifest_hash`` + ``signature``, then serialize with :meth:`to_json`.
    """

    version: str
    subject_id_hash: str  # "sha256:<hex>"
    salt_hash: str  # "sha256:<hex>" — hash of the salt (lets verifiers detect salt rotation)
    issued_at: datetime
    operator_id: str
    clauses: tuple[str, ...]
    stores: dict[str, dict[str, int | str]] = field(default_factory=dict)
    manifest_hash: str = ""  # "sha256:<hex>" — set by the signer
    signature: str = ""  # "ed25519:<hex>" — set by the signer
    verification_hint: str = "vismaran verify receipt.json --pubkey op.pub"

    @classmethod
    def build(
        cls,
        *,
        subject_id_hash: str,
        salt_hash: str,
        operator_id: str,
        clauses: tuple[str, ...],
        stores: dict[str, dict[str, int | str]],
        issued_at: datetime,
    ) -> Self:
        """Construct an unsigned receipt. The signer fills in the hash + signature."""
        return cls(
            version=VERSION,
            subject_id_hash=subject_id_hash,
            salt_hash=salt_hash,
            issued_at=issued_at,
            operator_id=operator_id,
            clauses=clauses,
            stores=stores,
        )

    def with_signature(self, *, manifest_hash: str, signature: str) -> Self:
        """Return a copy with the signing fields populated (used by the signer)."""
        return replace(self, manifest_hash=manifest_hash, signature=signature)

    def canonical_manifest(self) -> dict[str, object]:
        """The deterministic, signature-excluded view of the receipt.

        This is exactly the content the signer hashes. ``manifest_hash`` and
        ``signature`` are excluded (they're derived from this), as is the
        human-facing ``verification_hint``.
        """
        return {
            "version": self.version,
            "subject_id_hash": self.subject_id_hash,
            "salt_hash": self.salt_hash,
            "issued_at": self.issued_at.isoformat(),
            "operator_id": self.operator_id,
            "clauses": list(self.clauses),
            "stores": self.stores,
        }

    def to_json(self) -> str:
        """Canonical JSON (sorted keys, compact separators)."""
        raise NotImplementedError("Receipt serialization lands with the signer (SPEC.md).")

    @classmethod
    def from_json(cls, text: str) -> Self:
        raise NotImplementedError("Receipt deserialization lands with the signer (SPEC.md).")
