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

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Self

VERSION = "vismaran/v0.1"
DEFAULT_VERIFICATION_HINT = "vismaran verify receipt.json --pubkey op.pub"


def _canonical_dumps(obj: object) -> str:
    """The one canonical-JSON encoding the whole codebase shares.

    Pinned profile (see SPEC.md § Receipt format): UTF-8 (non-ASCII emitted
    literally, not ``\\u``-escaped), keys sorted recursively, no insignificant
    whitespace. A spec-compliant verifier in any language reproduces these
    bytes, so the signed hash is reproducible offline.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_timestamp(dt: datetime) -> str:
    """RFC 3339 UTC with a ``Z`` suffix — the single wire form the hash covers.

    A naive datetime is treated as UTC (deterministic) rather than silently
    localtime-converted; :meth:`Receipt.build` rejects naive input up front.
    """
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_counts(stores: dict[str, dict[str, int | str]]) -> None:
    """Counts must be exact integers; floats/bools have no canonical JSON form."""
    for store, fields in stores.items():
        for key, value in fields.items():
            # ``type(value) is int`` rejects bool (a subclass of int) and float.
            if isinstance(value, str) or type(value) is int:
                continue
            raise ValueError(
                f"store {store!r} field {key!r} must be int or str, "
                f"not {type(value).__name__} — receipt counts must be exact integers"
            )


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
    verification_hint: str = DEFAULT_VERIFICATION_HINT

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
        """Construct an unsigned receipt. The signer fills in the hash + signature.

        Raises:
            ValueError: ``issued_at`` is naive (no tzinfo), or a store count is
                not an exact integer — both would make the signed hash
                ambiguous across verifiers.
        """
        if issued_at.tzinfo is None:
            raise ValueError("issued_at must be timezone-aware (use datetime.now(UTC))")
        _validate_counts(stores)
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
            "issued_at": _canonical_timestamp(self.issued_at),
            "operator_id": self.operator_id,
            "clauses": list(self.clauses),
            "stores": self.stores,
        }

    def canonical_manifest_json(self) -> str:
        """Canonical JSON of the manifest subset — exactly what the signer hashes.

        Byte-for-byte deterministic (see :func:`_canonical_dumps`), so a verifier
        that re-serializes an equal receipt computes the same hash.
        """
        return _canonical_dumps(self.canonical_manifest())

    def to_json(self) -> str:
        """Canonical JSON of the full on-disk receipt (manifest + hash + sig + hint)."""
        full = {
            **self.canonical_manifest(),
            "manifest_hash": self.manifest_hash,
            "signature": self.signature,
            "verification_hint": self.verification_hint,
        }
        return _canonical_dumps(full)

    @classmethod
    def from_json(cls, text: str) -> Self:
        """Reconstruct a Receipt from :meth:`to_json` output (round-trips exactly)."""
        raw = json.loads(text)
        return cls(
            version=raw["version"],
            subject_id_hash=raw["subject_id_hash"],
            salt_hash=raw["salt_hash"],
            issued_at=datetime.fromisoformat(raw["issued_at"]),
            operator_id=raw["operator_id"],
            clauses=tuple(raw["clauses"]),
            stores=raw["stores"],
            manifest_hash=raw.get("manifest_hash", ""),
            signature=raw.get("signature", ""),
            verification_hint=raw.get("verification_hint", DEFAULT_VERIFICATION_HINT),
        )
