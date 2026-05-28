"""Receipt: canonical JSON, Ed25519 sign / verify, tampering rejection.

Pure unit tests — no docker. The receipt is metadata only (a salted hash of the
subject, per-store counts, operator + clauses); the signer operates *on* a
Receipt and lives in infrastructure. These tests pin the round-trip, the
tamper-evidence, and the "raw subject never leaks" invariant.
"""

from __future__ import annotations

import hashlib
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from vismaran.domain import ConfigurationError, Receipt
from vismaran.domain.receipt import VERSION
from vismaran.infrastructure.crypto import Ed25519ReceiptSigner

RAW_SUBJECT = "alice@example.com"


def _subject_id_hash(subject: str, salt: bytes) -> str:
    return "sha256:" + hashlib.sha256(salt + subject.encode()).hexdigest()


def _salt_hash(salt: bytes) -> str:
    return "sha256:" + hashlib.sha256(salt).hexdigest()


def _build_receipt(
    *,
    salt: bytes,
    subject: str = RAW_SUBJECT,
    stores: dict[str, dict[str, int | str]] | None = None,
) -> Receipt:
    return Receipt.build(
        subject_id_hash=_subject_id_hash(subject, salt),
        salt_hash=_salt_hash(salt),
        operator_id="acme-vismaran-deploy-01",
        clauses=("DPDP-2023:S12", "GDPR-Art17"),
        stores=stores
        or {
            "pgvector": {"embeddings_deleted": 230, "method": "provenance-driven delete"},
            "cognee": {"nodes_deleted": 14, "edges_deleted": 9, "method": "cypher tier-3"},
        },
        issued_at=datetime(2026, 5, 27, 15, 42, 1, tzinfo=UTC),
    )


@pytest.fixture
def signer_and_pubkey(tmp_path: Path) -> tuple[Ed25519ReceiptSigner, Path]:
    priv = tmp_path / "op.key"
    pub = Ed25519ReceiptSigner.generate_keypair(priv)
    return Ed25519ReceiptSigner(signing_key_path=priv), pub


# --- sign / verify ---------------------------------------------------------


def test_sign_then_verify_roundtrip(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    signer, pub = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))

    assert signed.manifest_hash.startswith("sha256:")
    assert signed.signature.startswith("ed25519:")
    assert signer.verify(signed, public_key_path=pub) is True


def test_tampered_field_fails_verify(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    signer, pub = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))

    # Inflate a deletion count after signing — the body no longer matches the
    # signed manifest hash.
    tampered = replace(
        signed,
        stores={"pgvector": {"embeddings_deleted": 999_999, "method": "provenance-driven delete"}},
    )
    assert signer.verify(tampered, public_key_path=pub) is False


def test_rewriting_manifest_hash_to_match_tampered_body_still_fails(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    """Defeat the obvious forge: change the body AND recompute manifest_hash.

    The signature covers the (original) hash, so it cannot validate the new one
    without the private key.
    """
    signer, pub = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))

    forged_stores = {"pgvector": {"embeddings_deleted": 0, "method": "provenance-driven delete"}}
    forged = replace(signed, stores=forged_stores)
    new_hash = "sha256:" + hashlib.sha256(forged.canonical_manifest_json().encode()).hexdigest()
    forged = replace(forged, manifest_hash=new_hash)  # body and hash now agree

    assert forged.manifest_hash != signed.manifest_hash
    assert signer.verify(forged, public_key_path=pub) is False


def test_inconsistent_manifest_hash_fails_verify(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    """If manifest_hash doesn't match the body, reject before touching the sig."""
    signer, pub = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))
    bogus = replace(signed, manifest_hash="sha256:" + "00" * 32)
    assert signer.verify(bogus, public_key_path=pub) is False


def test_verify_fails_against_wrong_public_key(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path],
    operator_salt: bytes,
    tmp_path: Path,
) -> None:
    signer, _ = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))

    other_pub = Ed25519ReceiptSigner.generate_keypair(tmp_path / "intruder.key")
    assert signer.verify(signed, public_key_path=other_pub) is False


def test_unsigned_receipt_does_not_verify(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    """A built-but-unsigned receipt (empty signature) must verify False, not raise."""
    signer, pub = signer_and_pubkey
    assert signer.verify(_build_receipt(salt=operator_salt), public_key_path=pub) is False


def test_sign_without_key_raises_configuration_error(operator_salt: bytes) -> None:
    signer = Ed25519ReceiptSigner(signing_key_path=None)
    with pytest.raises(ConfigurationError, match="signing key"):
        signer.sign(_build_receipt(salt=operator_salt))


@pytest.mark.parametrize(
    "field",
    ["manifest_hash", "signature"],
)
def test_garbage_signature_fields_return_false_not_raise(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path],
    operator_salt: bytes,
    field: str,
) -> None:
    """A verifier handed a malformed receipt reports INVALID — it must not crash."""
    signer, pub = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))
    garbage = replace(signed, **{field: "not-hex-ÿ-garbage"})
    assert signer.verify(garbage, public_key_path=pub) is False


def test_surrogate_in_manifest_hash_returns_false_not_raise(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    """A lone surrogate is valid JSON (survives from_json) but unencodable as UTF-8.

    It must not crash verify — a hostile on-disk receipt reports INVALID.
    """
    signer, pub = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))
    nasty = replace(signed, manifest_hash="sha256:\ud800")
    assert signer.verify(nasty, public_key_path=pub) is False


def test_surrogate_in_signed_field_returns_false_not_raise(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    """A lone surrogate in a SIGNED field flows through the digest, not just the
    hash field — verify must still report INVALID rather than crash."""
    signer, pub = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))
    nasty = replace(signed, operator_id="\ud800")
    assert signer.verify(nasty, public_key_path=pub) is False


# --- key generation --------------------------------------------------------


def test_generate_keypair_writes_private_and_public(tmp_path: Path) -> None:
    priv = tmp_path / "op.key"
    pub = Ed25519ReceiptSigner.generate_keypair(priv)

    assert pub == priv.with_suffix(".pub")
    assert priv.exists() and pub.exists()
    # Private key must not be world/group readable.
    mode = stat.S_IMODE(priv.stat().st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0, f"private key is too permissive: {mode:o}"


# --- canonical JSON --------------------------------------------------------


def test_canonical_json_is_sorted_and_compact(operator_salt: bytes) -> None:
    text = _build_receipt(salt=operator_salt).to_json()
    # Compact: no whitespace after separators.
    assert ", " not in text
    assert '": ' not in text
    # Top-level keys are sorted.
    import json

    keys = list(json.loads(text).keys())
    assert keys == sorted(keys)


def test_canonical_json_is_insertion_order_independent(operator_salt: bytes) -> None:
    a = _build_receipt(
        salt=operator_salt,
        stores={"cognee": {"nodes_deleted": 1}, "pgvector": {"embeddings_deleted": 2}},
    )
    b = _build_receipt(
        salt=operator_salt,
        stores={"pgvector": {"embeddings_deleted": 2}, "cognee": {"nodes_deleted": 1}},
    )
    assert a.to_json() == b.to_json()


def test_json_roundtrip_preserves_receipt(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    signer, _ = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))
    restored = Receipt.from_json(signed.to_json())
    assert restored == signed
    assert restored.version == VERSION


def test_loaded_receipt_still_verifies(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    """The on-disk → load → verify path a regulator actually walks."""
    signer, pub = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))
    restored = Receipt.from_json(signed.to_json())
    assert signer.verify(restored, public_key_path=pub) is True


# --- privacy + constant-size invariants ------------------------------------


def test_subject_id_never_appears_raw(operator_salt: bytes) -> None:
    """Receipts hold only the hashed subject_id — raw subject + salt must NEVER leak."""
    text = _build_receipt(salt=operator_salt).to_json()
    assert RAW_SUBJECT not in text
    assert operator_salt.decode() not in text


def test_signed_payload_is_constant_size_regardless_of_erasure(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    """The signed payload is a fixed 32-byte hash regardless of erasure size.

    A tiny erasure and a 1000-store erasure produce the same-length manifest
    hash, and both verify — so verification cost doesn't grow with the deletion.
    """
    signer, pub = signer_and_pubkey
    tiny = signer.sign(_build_receipt(salt=operator_salt, stores={"pgvector": {"x": 1}}))
    huge = signer.sign(
        _build_receipt(salt=operator_salt, stores={f"s{i}": {"x": i} for i in range(1000)})
    )

    def _hex(h: str) -> str:
        return h.removeprefix("sha256:")

    assert len(_hex(tiny.manifest_hash)) == 64
    assert len(_hex(huge.manifest_hash)) == len(_hex(tiny.manifest_hash))
    assert signer.verify(tiny, public_key_path=pub) is True
    assert signer.verify(huge, public_key_path=pub) is True


# --- canonicalization is pinned for cross-implementation verifiers ---------


def test_issued_at_serializes_as_rfc3339_z(operator_salt: bytes) -> None:
    """The wire form is UTC with a 'Z' suffix, not '+00:00' (matches SPEC.md)."""
    import json

    manifest = json.loads(_build_receipt(salt=operator_salt).canonical_manifest_json())
    assert manifest["issued_at"] == "2026-05-27T15:42:01Z"


def test_non_utc_issued_at_is_normalized_to_utc_z(operator_salt: bytes) -> None:
    """A +05:30 timestamp canonicalizes to the same instant in UTC 'Z' form."""
    import json

    ist = timezone(timedelta(hours=5, minutes=30))
    r = Receipt.build(
        subject_id_hash=_subject_id_hash(RAW_SUBJECT, operator_salt),
        salt_hash=_salt_hash(operator_salt),
        operator_id="acme-vismaran-deploy-01",
        clauses=("GDPR-Art17",),
        stores={"pgvector": {"embeddings_deleted": 1}},
        issued_at=datetime(2026, 5, 27, 21, 12, 1, tzinfo=ist),  # == 15:42:01Z
    )
    assert json.loads(r.canonical_manifest_json())["issued_at"] == "2026-05-27T15:42:01Z"


def test_build_rejects_naive_datetime(operator_salt: bytes) -> None:
    """A naive issued_at is ambiguous across operators — fail loud at build."""
    with pytest.raises(ValueError, match="timezone-aware"):
        Receipt.build(
            subject_id_hash=_subject_id_hash(RAW_SUBJECT, operator_salt),
            salt_hash=_salt_hash(operator_salt),
            operator_id="op",
            clauses=("GDPR-Art17",),
            stores={"pgvector": {"embeddings_deleted": 1}},
            issued_at=datetime(2026, 5, 27, 15, 42, 1),  # naive on purpose
        )


@pytest.mark.parametrize("bad_count", [230.0, True])
def test_build_rejects_non_integer_counts(operator_salt: bytes, bad_count: object) -> None:
    """Floats and bools have no canonical JSON form — reject before signing."""
    with pytest.raises(ValueError, match="exact integers"):
        Receipt.build(
            subject_id_hash=_subject_id_hash(RAW_SUBJECT, operator_salt),
            salt_hash=_salt_hash(operator_salt),
            operator_id="op",
            clauses=("GDPR-Art17",),
            stores={"pgvector": {"embeddings_deleted": bad_count}},  # type: ignore[dict-item]
            issued_at=datetime(2026, 5, 27, 15, 42, 1, tzinfo=UTC),
        )


def test_canonical_manifest_is_exact_utf8_bytes(operator_salt: bytes) -> None:
    """Pin the byte sequence: non-ASCII is emitted literally (UTF-8), keys sorted.

    This is the cross-implementation contract — a verifier in another language
    that follows the SPEC profile must reproduce *these* bytes. If this string
    ever changes, every previously-issued receipt stops verifying.
    """
    r = Receipt.build(
        subject_id_hash="sha256:" + "ab" * 32,
        salt_hash="sha256:" + "cd" * 32,
        operator_id="açme-deploy",  # non-ASCII: must NOT be \u-escaped
        clauses=("GDPR-Art17",),
        stores={"pgvector": {"embeddings_deleted": 2}},
        issued_at=datetime(2026, 5, 27, 15, 42, 1, tzinfo=UTC),
    )
    expected = (
        "{"
        '"clauses":["GDPR-Art17"],'
        '"issued_at":"2026-05-27T15:42:01Z",'
        '"operator_id":"açme-deploy",'
        f'"salt_hash":"sha256:{"cd" * 32}",'
        '"stores":{"pgvector":{"embeddings_deleted":2}},'
        f'"subject_id_hash":"sha256:{"ab" * 32}",'
        '"version":"vismaran/v0.1"'
        "}"
    )
    assert r.canonical_manifest_json() == expected
    # And the raw bytes are UTF-8 (the literal é is two bytes, not six \u chars).
    assert "ç".encode() in r.canonical_manifest_json().encode()
    assert "\\u" not in r.canonical_manifest_json()


# --- pubkey errors are distinct from a forged receipt ----------------------


def test_verify_raises_on_missing_public_key(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes, tmp_path: Path
) -> None:
    signer, _ = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))
    with pytest.raises(ConfigurationError, match="not readable"):
        signer.verify(signed, public_key_path=tmp_path / "does-not-exist.pub")


def test_verify_raises_on_corrupt_public_key(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes, tmp_path: Path
) -> None:
    signer, _ = signer_and_pubkey
    signed = signer.sign(_build_receipt(salt=operator_salt))
    corrupt = tmp_path / "corrupt.pub"
    corrupt.write_text("-----BEGIN PUBLIC KEY-----\nnot base64\n-----END PUBLIC KEY-----\n")
    with pytest.raises(ConfigurationError, match="not valid PEM"):
        signer.verify(signed, public_key_path=corrupt)


# --- signature cannot be replayed onto another subject's receipt -----------


def test_signature_cannot_be_replayed_across_subjects(
    signer_and_pubkey: tuple[Ed25519ReceiptSigner, Path], operator_salt: bytes
) -> None:
    """Splice subject A's signature onto subject B's body → must fail."""
    signer, pub = signer_and_pubkey
    alice = signer.sign(_build_receipt(salt=operator_salt, subject="alice@example.com"))
    bob = _build_receipt(salt=operator_salt, subject="bob@example.com")

    forged = replace(bob, manifest_hash=alice.manifest_hash, signature=alice.signature)
    assert signer.verify(forged, public_key_path=pub) is False
