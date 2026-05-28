"""Ed25519 receipt signer/verifier.

Operates *on* a domain ``Receipt`` — the Receipt value object itself imports no
crypto library; this is where the actual signing lives. Keeping it in the
infrastructure layer means the domain stays pure and the signing scheme can
evolve (key formats, hash choices) without touching the domain model.

The signed payload is a SHA-256 hash over the receipt's canonical manifest
(see ``Receipt.canonical_manifest``), so verification is constant-time
regardless of how large the erasure was.

Implementation lands with the receipt milestone (SPEC.md § Receipt format).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from vismaran.domain.receipt import Receipt


class Ed25519ReceiptSigner:
    """Signs and verifies :class:`~vismaran.domain.receipt.Receipt` objects."""

    def __init__(self, *, signing_key_path: Path | None = None) -> None:
        self._signing_key_path = signing_key_path

    def sign(self, receipt: Receipt) -> Receipt:
        """Return a copy of ``receipt`` with ``manifest_hash`` + ``signature`` set."""
        raise NotImplementedError("Ed25519 signing lands with the receipt milestone (SPEC.md).")

    def verify(self, receipt: Receipt, *, public_key_path: Path) -> bool:
        """Return True iff the receipt's signature is valid for the given pubkey."""
        raise NotImplementedError(
            "Ed25519 verification lands with the receipt milestone (SPEC.md)."
        )

    @staticmethod
    def generate_keypair(out_path: Path) -> Path:
        """Generate an Ed25519 keypair; write the private key to ``out_path``.

        Returns the public-key path (``out_path`` with a ``.pub`` suffix).
        """
        raise NotImplementedError("Key generation lands with the receipt milestone (SPEC.md).")
