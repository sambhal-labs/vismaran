"""Ed25519 receipt signer/verifier.

Operates *on* a domain ``Receipt`` — the Receipt value object itself imports no
crypto library; this is where the actual signing lives. Keeping it in the
infrastructure layer means the domain stays pure and the signing scheme can
evolve (key formats, hash choices) without touching the domain model.

The signed payload is a SHA-256 digest over the receipt's canonical manifest
(see ``Receipt.canonical_manifest_json``), so the signed/verified payload is a
constant 32 bytes regardless of how large the erasure was.

Verification is two-stage: (1) the receipt's ``manifest_hash`` must match a
fresh hash of its body — catches a receipt whose stated hash disagrees with its
contents; (2) the Ed25519 signature must validate over that digest — catches
anyone who edits the body (and the hash) without the private key. A malformed
*receipt* yields ``False`` (never an exception); an unreadable or invalid
*public key* is a configuration error and raises ``ConfigurationError`` — a
distinct signal from "this receipt is forged".
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from vismaran.domain.errors import ConfigurationError

if TYPE_CHECKING:
    from pathlib import Path

    from vismaran.domain.receipt import Receipt

_SHA256_PREFIX = "sha256:"
_ED25519_PREFIX = "ed25519:"


class Ed25519ReceiptSigner:
    """Signs and verifies :class:`~vismaran.domain.receipt.Receipt` objects."""

    def __init__(self, *, signing_key_path: Path | None = None) -> None:
        self._signing_key_path = signing_key_path

    def sign(self, receipt: Receipt) -> Receipt:
        """Return a copy of ``receipt`` with ``manifest_hash`` + ``signature`` set."""
        if self._signing_key_path is None:
            raise ConfigurationError("no signing key configured; cannot sign a receipt")
        private_key = self._load_private_key(self._signing_key_path)
        digest = self._manifest_digest(receipt)
        signature = private_key.sign(digest)
        return receipt.with_signature(
            manifest_hash=_SHA256_PREFIX + digest.hex(),
            signature=_ED25519_PREFIX + signature.hex(),
        )

    def verify(self, receipt: Receipt, *, public_key_path: Path) -> bool:
        """Return True iff the receipt's signature is valid for the given pubkey.

        A malformed/tampered receipt returns ``False``. An unreadable or invalid
        public-key file raises ``ConfigurationError`` (you gave us no key to
        check against — a different failure from "the receipt is forged").
        """
        digest = self._manifest_digest(receipt)
        expected_hash = _SHA256_PREFIX + digest.hex()
        # 1. The stored hash must match the body it claims to cover. Compare as
        # bytes so a hand-crafted manifest_hash yields False, not an exception —
        # a verifier handed garbage reports INVALID, not crash. ``surrogatepass``
        # tolerates lone surrogates (valid JSON, survive from_json) that plain
        # UTF-8 encoding would reject; expected_hash is ASCII so it can't match.
        stored_hash = receipt.manifest_hash.encode("utf-8", "surrogatepass")
        if not hmac.compare_digest(expected_hash.encode(), stored_hash):
            return False
        # 2. The signature must validate as Ed25519 over that digest.
        if not receipt.signature.startswith(_ED25519_PREFIX):
            return False
        try:
            signature = bytes.fromhex(receipt.signature.removeprefix(_ED25519_PREFIX))
        except ValueError:
            return False
        public_key = self._load_public_key(public_key_path)
        try:
            public_key.verify(signature, digest)
        except InvalidSignature:
            return False
        return True

    @staticmethod
    def generate_keypair(out_path: Path) -> Path:
        """Generate an Ed25519 keypair; write the private key to ``out_path``.

        The private key is written ``0600`` (created restricted, and re-chmod'd
        in case the path pre-existed with looser perms). Returns the public-key
        path (``out_path`` with its suffix replaced by ``.pub``).
        """
        private_key = Ed25519PrivateKey.generate()
        priv_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pub_path = out_path.with_suffix(".pub")
        fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(priv_pem)
        out_path.chmod(0o600)
        pub_path.write_bytes(pub_pem)
        return pub_path

    # --- internals ---------------------------------------------------------

    @staticmethod
    def _manifest_digest(receipt: Receipt) -> bytes:
        # ``surrogatepass``: a hostile receipt loaded from disk can carry lone
        # surrogates in a signed field (valid JSON, unencodable as strict UTF-8).
        # Encode them deterministically rather than crashing — the digest simply
        # won't match any real signature, so verify() returns False. Legitimate
        # receipts contain no surrogates, so this is byte-identical for them.
        manifest = receipt.canonical_manifest_json().encode("utf-8", "surrogatepass")
        return hashlib.sha256(manifest).digest()

    @staticmethod
    def _load_private_key(path: Path) -> Ed25519PrivateKey:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ConfigurationError(f"signing key not readable: {path}") from exc
        key = serialization.load_pem_private_key(raw, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ConfigurationError(f"signing key at {path} is not an Ed25519 private key")
        return key

    @staticmethod
    def _load_public_key(path: Path) -> Ed25519PublicKey:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ConfigurationError(f"public key not readable: {path}") from exc
        try:
            key = serialization.load_pem_public_key(raw)
        except ValueError as exc:
            raise ConfigurationError(f"public key at {path} is not valid PEM") from exc
        if not isinstance(key, Ed25519PublicKey):
            raise ConfigurationError(f"public key at {path} is not an Ed25519 public key")
        return key
