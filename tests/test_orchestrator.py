"""Orchestrator semantics: fan-out, dry-run, fail-loud, idempotency, receipt.

Unit tests with in-memory fake adapters + a fake provenance store, but a REAL
Ed25519 signer — so "commit emits a signed receipt" is verified end to end
(the receipt actually validates), not asserted against a mock. Cross-adapter
behavior against live stores is covered by ``test_orchestrator_integration``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vismaran.application import Orchestrator
from vismaran.domain import (
    AdapterKind,
    ConfigurationError,
    Mode,
    PartialErasureError,
    PerStoreResult,
    ProvenanceRecord,
    RecordId,
    Scope,
    SubjectId,
)
from vismaran.infrastructure.crypto import Ed25519ReceiptSigner

SALT = b"unit-test-salt-32-bytes-long!!aa"  # >= 16 bytes
SUBJECT = "alice@example.com"


class FakeAdapter:
    """A StoreAdapter that records calls and can be told to fail on commit."""

    def __init__(
        self,
        name: str,
        kind: AdapterKind,
        *,
        counts: dict[str, int] | None = None,
        fail: bool = False,
        fail_preview: bool = False,
        return_failed: bool = False,
    ) -> None:
        self.name = name
        self.kind = kind
        self._counts = counts or {}
        self.fail = fail
        self.fail_preview = fail_preview
        self.return_failed = return_failed
        self.preview_calls = 0
        self.commit_calls = 0

    async def preview(
        self, subject: SubjectId, *, scope: Scope, provenance: list[ProvenanceRecord]
    ) -> PerStoreResult:
        self.preview_calls += 1
        if self.fail_preview:
            raise RuntimeError(f"{self.name} preview boom for subject {subject}")
        return PerStoreResult(self.name, self.kind, dict(self._counts), "fake preview")

    async def erase(
        self,
        subject: SubjectId,
        *,
        scope: Scope,
        mode: Mode,
        provenance: list[ProvenanceRecord],
    ) -> PerStoreResult:
        if mode == Mode.DRY_RUN:
            return await self.preview(subject, scope=scope, provenance=provenance)
        self.commit_calls += 1
        if self.return_failed:
            # An adapter can report failure WITHOUT raising — the orchestrator
            # must treat succeeded=False as a failure too.
            return PerStoreResult(
                self.name,
                self.kind,
                {},
                "self-reported failure",
                succeeded=False,
                error="downstream",
            )
        if self.fail:
            # Message embeds the raw subject on purpose — the orchestrator must
            # NOT propagate it into the (potentially logged) PerStoreResult.error.
            raise RuntimeError(f"{self.name} downstream boom for subject {subject}")
        return PerStoreResult(self.name, self.kind, dict(self._counts), "fake erase")

    async def health_check(self) -> bool:
        return True


class FailingSigner:
    """A ReceiptSigner whose sign() always raises (e.g. key vault unreachable)."""

    def sign(self, receipt: object) -> object:
        raise RuntimeError("signing key vault unreachable")


class FakeProvenanceStore:
    def __init__(self, records: list[ProvenanceRecord] | None = None) -> None:
        self._records = list(records or [])
        self.purge_calls = 0

    async def lookup(self, subject_id: SubjectId | str) -> list[ProvenanceRecord]:
        return list(self._records)

    async def purge(self, subject_id: SubjectId | str) -> int:
        self.purge_calls += 1
        n = len(self._records)
        self._records = []
        return n

    # Present so the fake satisfies the ProvenanceStore Protocol surface.
    async def record(self, **kwargs: object) -> None: ...

    async def lookup_by_framework(
        self, subject_id: SubjectId | str, framework: str
    ) -> list[ProvenanceRecord]:
        return [r for r in self._records if r.framework == framework]

    async def count(self, subject_id: SubjectId | str) -> int:
        return len(self._records)


def _rec(framework: str = "pgvector") -> ProvenanceRecord:
    return ProvenanceRecord(
        subject_id=SubjectId(SUBJECT),
        framework=framework,
        record_id=RecordId(str(uuid.uuid4())),
        write_ts=datetime.now(tz=UTC),
    )


@pytest.fixture
def signer_and_pub(tmp_path: Path) -> tuple[Ed25519ReceiptSigner, Path]:
    priv = tmp_path / "op.key"
    pub = Ed25519ReceiptSigner.generate_keypair(priv)
    return Ed25519ReceiptSigner(signing_key_path=priv), pub


def _orch(
    signer: Ed25519ReceiptSigner,
    adapters: list[FakeAdapter],
    provenance: FakeProvenanceStore,
) -> Orchestrator:
    return Orchestrator(
        provenance=provenance,
        adapters=adapters,  # type: ignore[arg-type]
        signer=signer,
        subject_salt=SALT,
        operator_id="acme-vismaran-deploy-01",
    )


# --- construction guards ---------------------------------------------------


def test_short_salt_rejected(signer_and_pub: tuple[Ed25519ReceiptSigner, Path]) -> None:
    signer, _ = signer_and_pub
    with pytest.raises(ConfigurationError, match="salt"):
        Orchestrator(
            provenance=FakeProvenanceStore(),
            adapters=[FakeAdapter("V", AdapterKind.VECTOR)],  # type: ignore[list-item]
            signer=signer,
            subject_salt=b"too-short",
            operator_id="op",
        )


def test_no_adapters_rejected(signer_and_pub: tuple[Ed25519ReceiptSigner, Path]) -> None:
    signer, _ = signer_and_pub
    with pytest.raises(ConfigurationError, match="adapter"):
        _orch(signer, [], FakeProvenanceStore())


def test_duplicate_adapter_kind_rejected(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    """v0 keys the receipt by layer (graph/vector/log) — two of a kind would collide."""
    signer, _ = signer_and_pub
    dupes = [FakeAdapter("A", AdapterKind.VECTOR), FakeAdapter("B", AdapterKind.VECTOR)]
    with pytest.raises(ConfigurationError, match="duplicate"):
        _orch(signer, dupes, FakeProvenanceStore())


# --- dry-run (preview) -----------------------------------------------------


async def test_preview_returns_results_without_mutating(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    signer, _ = signer_and_pub
    g = FakeAdapter("CogneeGraphAdapter", AdapterKind.GRAPH, counts={"nodes_deleted": 3})
    v = FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR, counts={"embeddings_matched": 5})
    prov = FakeProvenanceStore(records=[_rec()])
    orch = _orch(signer, [g, v], prov)

    results = await orch.preview(SubjectId(SUBJECT))

    assert {r.kind for r in results} == {AdapterKind.GRAPH, AdapterKind.VECTOR}
    assert g.commit_calls == 0 and v.commit_calls == 0  # no mutation
    assert g.preview_calls == 1 and v.preview_calls == 1
    assert prov.purge_calls == 0  # preview NEVER purges provenance


# --- commit (erase) --------------------------------------------------------


async def test_commit_emits_signed_verifiable_receipt(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    signer, pub = signer_and_pub
    g = FakeAdapter(
        "CogneeGraphAdapter", AdapterKind.GRAPH, counts={"nodes_deleted": 14, "edges_deleted": 9}
    )
    v = FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR, counts={"embeddings_deleted": 230})
    log = FakeAdapter("TensorZeroLogAdapter", AdapterKind.LOG, counts={"chat_inference_rows": 5})
    prov = FakeProvenanceStore(records=[_rec(), _rec()])
    orch = _orch(signer, [g, v, log], prov)

    receipt = await orch.erase(SubjectId(SUBJECT))

    assert signer.verify(receipt, public_key_path=pub) is True
    assert {"graph", "vector", "log", "provenance"} <= set(receipt.stores)
    assert receipt.stores["vector"]["embeddings_deleted"] == 230
    assert receipt.stores["graph"]["method"]  # adapter method carried through
    assert receipt.stores["provenance"]["rows_purged"] == 2
    assert receipt.operator_id == "acme-vismaran-deploy-01"
    assert receipt.clauses  # default DPDP/GDPR clauses populated
    assert prov.purge_calls == 1


async def test_receipt_never_contains_raw_subject(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    signer, _ = signer_and_pub
    v = FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR, counts={"embeddings_deleted": 1})
    orch = _orch(signer, [v], FakeProvenanceStore(records=[_rec()]))

    receipt = await orch.erase(SubjectId(SUBJECT))

    assert SUBJECT not in receipt.to_json()
    assert receipt.subject_id_hash.startswith("sha256:")
    assert receipt.salt_hash.startswith("sha256:")


async def test_fans_out_to_every_adapter(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    signer, _ = signer_and_pub
    adapters = [
        FakeAdapter("CogneeGraphAdapter", AdapterKind.GRAPH),
        FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR),
        FakeAdapter("TensorZeroLogAdapter", AdapterKind.LOG),
    ]
    orch = _orch(signer, adapters, FakeProvenanceStore())

    await orch.erase(SubjectId(SUBJECT))

    assert all(a.commit_calls == 1 for a in adapters)


# --- fail-loud -------------------------------------------------------------


async def test_partial_failure_raises_and_signs_no_receipt(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    signer, _ = signer_and_pub
    ok = FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR, counts={"embeddings_deleted": 1})
    bad = FakeAdapter("TensorZeroLogAdapter", AdapterKind.LOG, fail=True)
    prov = FakeProvenanceStore(records=[_rec()])
    orch = _orch(signer, [ok, bad], prov)

    with pytest.raises(PartialErasureError) as excinfo:
        await orch.erase(SubjectId(SUBJECT))

    err = excinfo.value
    by_name = {r.adapter_name: r for r in err.per_adapter}
    assert by_name["TensorZeroLogAdapter"].succeeded is False
    assert by_name["PgvectorVectorAdapter"].succeeded is True
    assert err.operation_id  # correlation id for a deterministic retry
    # The failure summary must not leak the raw subject (the message contained it).
    assert SUBJECT not in (by_name["TensorZeroLogAdapter"].error or "")
    # Fail-loud contract: provenance is NOT purged when any adapter fails.
    assert prov.purge_calls == 0


async def test_retry_after_failure_succeeds_and_purges_once(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    signer, pub = signer_and_pub
    ok = FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR, counts={"embeddings_deleted": 1})
    flaky = FakeAdapter("TensorZeroLogAdapter", AdapterKind.LOG, counts={"chat_inference_rows": 2})
    flaky.fail = True
    prov = FakeProvenanceStore(records=[_rec()])
    orch = _orch(signer, [ok, flaky], prov)

    with pytest.raises(PartialErasureError):
        await orch.erase(SubjectId(SUBJECT))
    assert prov.purge_calls == 0

    flaky.fail = False  # operator fixes the downstream
    receipt = await orch.erase(SubjectId(SUBJECT))

    assert signer.verify(receipt, public_key_path=pub) is True
    assert prov.purge_calls == 1  # purged only on the run that fully succeeded


# --- idempotency -----------------------------------------------------------


async def test_second_run_is_idempotent_noop_receipt(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    """A re-run after success returns a valid receipt asserting zero provenance left."""
    signer, pub = signer_and_pub
    v = FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR, counts={"embeddings_deleted": 3})
    prov = FakeProvenanceStore(records=[_rec()])
    orch = _orch(signer, [v], prov)

    first = await orch.erase(SubjectId(SUBJECT))
    second = await orch.erase(SubjectId(SUBJECT))

    assert signer.verify(second, public_key_path=pub) is True
    assert first.stores["provenance"]["rows_purged"] == 1
    assert second.stores["provenance"]["rows_purged"] == 0  # nothing left to purge
    assert prov.purge_calls == 2


# --- edge cases the reviewer flagged ---------------------------------------


async def test_preview_failure_is_redacted_not_raised(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    """A store that can't be previewed comes back succeeded=False, subject redacted."""
    signer, _ = signer_and_pub
    ok = FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR, counts={"embeddings_matched": 5})
    bad = FakeAdapter("TensorZeroLogAdapter", AdapterKind.LOG, fail_preview=True)
    orch = _orch(signer, [ok, bad], FakeProvenanceStore(records=[_rec()]))

    results = await orch.preview(SubjectId(SUBJECT))  # must NOT raise

    by_name = {r.adapter_name: r for r in results}
    assert by_name["PgvectorVectorAdapter"].succeeded is True
    assert by_name["TensorZeroLogAdapter"].succeeded is False
    assert SUBJECT not in (by_name["TensorZeroLogAdapter"].error or "")


async def test_adapter_self_reporting_failure_blocks_purge_and_receipt(
    signer_and_pub: tuple[Ed25519ReceiptSigner, Path],
) -> None:
    """An adapter returning succeeded=False (without raising) is still a failure."""
    signer, _ = signer_and_pub
    ok = FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR, counts={"embeddings_deleted": 1})
    sad = FakeAdapter("TensorZeroLogAdapter", AdapterKind.LOG, return_failed=True)
    prov = FakeProvenanceStore(records=[_rec()])
    orch = _orch(signer, [ok, sad], prov)

    with pytest.raises(PartialErasureError):
        await orch.erase(SubjectId(SUBJECT))
    assert prov.purge_calls == 0


async def test_signer_failure_propagates_after_adapters_succeed() -> None:
    """If signing fails after a successful fan-out, the error surfaces (not swallowed).

    Documents the purge-then-sign ordering: the provenance purge has already run.
    """
    ok = FakeAdapter("PgvectorVectorAdapter", AdapterKind.VECTOR, counts={"embeddings_deleted": 1})
    prov = FakeProvenanceStore(records=[_rec()])
    orch = Orchestrator(
        provenance=prov,
        adapters=[ok],  # type: ignore[list-item]
        signer=FailingSigner(),  # type: ignore[arg-type]
        subject_salt=SALT,
        operator_id="op",
    )

    with pytest.raises(RuntimeError, match="signing key vault"):
        await orch.erase(SubjectId(SUBJECT))
    assert prov.purge_calls == 1
