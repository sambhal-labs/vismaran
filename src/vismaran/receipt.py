"""Signed deletion receipts.

A receipt is canonical JSON signed with an Ed25519 key. The signed payload is a
SHA-256 hash of the canonicalized manifest, not the full manifest body, so
verification is constant-time regardless of erasure size.

The receipt holds **metadata only**: a hash of the subject ID (with a
per-deployment salt), per-store counts, the operator ID, the clause(s) the
action satisfies, and a timestamp. The raw subject ID never appears in a
receipt — that would defeat the point of erasing it.

Implementation lands Day 5. Today (Day 1) we lock the public surface so the
orchestrator, CLI, and adapters can import against it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from vismaran.types import PerStoreResult

VERSION = "vismaran/v0.1"


@dataclass(frozen=True, slots=True)
class Receipt:
    """Canonical deletion receipt.

    Fields are write-once at construction (the dataclass is frozen). Use
    :meth:`sign` to produce a signed copy, :meth:`verify` to check one, and
    :meth:`to_json` / :meth:`from_json` to round-trip.
    """

    version: str
    subject_id_hash: str  # "sha256:<hex>"
    salt_hash: (
        str  # "sha256:<hex>" — hash of the salt itself (lets verify code detect salt rotation)
    )
    issued_at: datetime
    operator_id: str
    clauses: tuple[str, ...]
    stores: dict[str, dict[str, int | str]] = field(default_factory=dict)
    manifest_hash: str = ""  # "sha256:<hex>" — set by sign()
    signature: str = ""  # "ed25519:<hex>" — set by sign()
    verification_hint: str = "vismaran verify receipt.json --pubkey op.pub"

    # --- construction ---

    @classmethod
    def build(
        cls,
        *,
        subject_id: str,
        salt: bytes,
        operator_id: str,
        clauses: tuple[str, ...],
        per_adapter: list[PerStoreResult],
        issued_at: datetime | None = None,
    ) -> Self:
        """Construct an unsigned receipt from per-adapter results."""
        raise NotImplementedError("Day 5 — see SPEC.md § Receipt format")

    # --- signing & verification ---

    def sign(self, signing_key_path: Path) -> Self:
        """Return a new Receipt with manifest_hash + signature populated.

        Uses Ed25519. The signing key file must be 32 bytes (raw private key)
        or PEM-encoded. ``vismaran keygen`` produces both.
        """
        raise NotImplementedError("Day 5 — see SPEC.md § Receipt format")

    def verify(self, public_key_path: Path) -> bool:
        """Return True iff the receipt's signature is valid for the given pubkey.

        ConstantTime by design — never short-circuits on partial mismatch.
        """
        raise NotImplementedError("Day 5 — see SPEC.md § Receipt format")

    # --- JSON round-trip ---

    def to_json(self) -> str:
        """Canonical JSON representation (sorted keys, no whitespace)."""
        raise NotImplementedError("Day 5 — see SPEC.md § Receipt format")

    @classmethod
    def from_json(cls, text: str) -> Self:
        raise NotImplementedError("Day 5 — see SPEC.md § Receipt format")
