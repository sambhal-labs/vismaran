# Vismaran — Specification

> v0.1 draft, 2026-05-27. This is a **living document**; sections marked ⏳ land later in the sprint.

## Goal

Given a subject identifier (an email, a phone number, a stable opaque user ID — whatever the operator chose at ingest), Vismaran erases every trace of that subject from an AI agent's live memory, and emits a signed deletion receipt that a regulator can verify offline without contacting Vismaran or the operator. The operator can hand a regulator three things and that should suffice: (1) the receipt, (2) the public verification key, (3) Vismaran's CLI binary.

Out of scope: backups, off-platform copies, model weights that already trained on the subject's data. Those need separate controls; see [Threat model](docs/architecture/4-threat.mmd).

## Architecture in one paragraph

A subject's data lives in three layers — graph (Cognee on Neo4j), vector (pgvector), log (TensorZero on ClickHouse). At ingest, the `vismaran_sdk` wrappers record a row per write into a provenance index (Postgres) — `(subject_id, framework, record_id, write_ts)`. At erasure, the orchestrator looks up every provenance row for the subject, fans out to the three adapters in parallel, each adapter performs framework-specific deletion (with a Cypher fallback for Cognee's tier-3 "subject mentioned in someone else's content" case), and on success the orchestrator signs a canonical-JSON receipt with an Ed25519 key. On any adapter failure, the orchestrator raises `PartialErasureError` — fail-loud, **no partial-commit receipt**.

## Erasure semantics

### Modes

- **`dry_run=True`** — query only. Adapters return projected counts; nothing is mutated; no receipt is emitted.
- **`dry_run=False`** (commit) — execute the erasure, write the receipt to disk, and return it. Idempotent: a second run for the same subject is a no-op that returns a receipt asserting zero rows affected this time.

### Scopes

- **Subject scope** (`subject="alice@example.com"`, the v0 default) — every provenance row tied to that subject.
- **Dataset / tenant scope** — Cognee tier-2 path; deletes a whole dataset. Use for tenant-level offboarding.
- ⏳ Time-range scope (v0.2).

### Failure semantics

Adapter failures are fail-loud. If any of the three adapters cannot complete the erasure to its store (e.g., ClickHouse mutation rejected, pgvector unreachable, Neo4j returns a constraint violation), the orchestrator:

1. Does **not** sign a receipt.
2. Raises `PartialErasureError` with per-adapter status (which succeeded, which failed, what was already erased).
3. Marks the operation `in_progress=true` in the local audit log so an operator can retry deterministically without re-processing the succeeded adapters.

We considered partial-commit receipts (sign what was done, leave the rest for next try) and rejected them — a partial receipt is worse than no receipt, because it lets an operator hand a regulator a document that *looks* complete but isn't.

## Adapters (v0)

### CogneeGraphAdapter — three-tier strategy

Based on Day-1 spike against Cognee v1.1.0 (released 2026-05-16).

1. **If subject IS a Cognee user:** `await cognee.forget(everything=True, user=resolved_user)`. Native, cascade is complete.
2. **If subject IS a dataset name:** `await cognee.forget(dataset=subject_id)`. Same cascade.
3. **If subject is a string mentioned inside someone else's content** — the actual GDPR case: Cypher fallback against `__Node__` universal label. Find `Entity{name CONTAINS $subject}`, find `DocumentChunk` / `Triplet` neighborhood, `DETACH DELETE` what's subject-only, regex-redact + re-embed what's mixed-content. **This third tier is the wedge — no Cognee API addresses it as of 2026-05-27.**

PII strings live in `Entity.name`, `DocumentChunk.text`, `Triplet.text`. Vector collections named `{NodeType}_{indexed_field}`; mirror every graph delete with `vector_engine.delete_data_points(collection, [slugs])`.

### PgvectorVectorAdapter — lineage-driven

Each embedding has a provenance row. Find embeddings for the subject via the provenance index, `DELETE FROM ${table} WHERE id IN (...)`. No magic — just enforces the rule "you can't erase what you didn't trace."

### TensorZeroLogAdapter — tag-scoped ClickHouse mutations

Based on Day-1 spike against TensorZero (latest, 2026-05).

- Ingest tags `vismaran::subject_id` on `/inference` and `/feedback` (TZ reserves `tensorzero::`).
- Erasure issues `ALTER TABLE ... DELETE WHERE tags['vismaran::subject_id'] = {sid}` on 6 tables: `ChatInference`, `JsonInference`, `BooleanMetricFeedback`, `FloatMetricFeedback`, `CommentFeedback`, `DemonstrationFeedback`.
- **Critical:** `ModelInference` has no `tags` column. Must cascade via `inference_id IN (...)` joined off `ChatInference.id ∪ JsonInference.id`. This is where the raw provider request/response bodies live — forgetting it leaves the leak open.
- Pre-query `SELECT count()` per table for the signed receipt.
- Use `InferenceTag` / `FeedbackTag` materialized views for fast reverse lookups when subject volumes are high.

## Receipt format

Canonical JSON, signed with Ed25519. The signed payload includes a SHA-256 hash of the canonical manifest; signature covers the hash, not the full body, so verification is constant-time regardless of erasure size.

```json
{
  "version": "vismaran/v0.1",
  "subject_id_hash": "sha256:8f4e…",
  "salt_hash": "sha256:af33…",
  "issued_at": "2026-05-27T15:42:01Z",
  "operator_id": "your-company-vismaran-deploy-01",
  "clauses": ["DPDP-2023:S12", "GDPR-Art17"],
  "stores": {
    "cognee": {"nodes_deleted": 14, "edges_deleted": 9, "chunks_redacted": 3, "embeddings_updated": 12, "method": "cognee.forget(dataset) + cypher tier-3"},
    "pgvector": {"embeddings_deleted": 230, "method": "provenance-driven delete"},
    "tensorzero": {"chat_inference_rows": 412, "json_inference_rows": 0, "model_inference_rows": 412, "boolean_feedback_rows": 8, "float_feedback_rows": 0, "comment_feedback_rows": 3, "demonstration_feedback_rows": 0, "method": "ALTER TABLE DELETE WHERE tags + inference_id cascade"}
  },
  "manifest_hash": "sha256:c1d2…",
  "signature": "ed25519:…",
  "verification_hint": "vismaran verify receipt.json --pubkey op.pub"
}
```

**Why hash the subject_id:** the receipt is metadata the operator must keep, sometimes indefinitely. Storing the raw subject ID after we just erased it would be self-defeating. The hash + salt lets a regulator confirm "this receipt is for subject X" by re-hashing X with the salt, without leaking X to anyone else who reads the receipt.

## DPDP / GDPR clause mapping

Concise table of which clause(s) each capability satisfies (expanded as the receipt milestone lands).

| Clause | What it requires | Vismaran capability |
|---|---|---|
| DPDP 2023 §12 | Data principal can demand erasure; data fiduciary must comply within a reasonable period | `vismaran erase --subject ...` |
| DPDP Rules 2025 (May 2027) | 90-day SLA, processor cascade, retained deletion record | Orchestrator clock + adapter fan-out + signed receipt |
| GDPR Art. 17(1) | "Right to erasure ('right to be forgotten')" | Subject-scope erasure |
| GDPR Art. 17(2) | Cascade to processors | Adapter protocol |
| GDPR Art. 5(1)(f) | Integrity and confidentiality of personal data | Signed receipt, hashed subject |
| GDPR Art. 30 | Records of processing activities | Local audit log (Postgres) |

## Provenance contract — what the operator must do

```python
from vismaran_sdk.tag import with_subject
from vismaran_sdk.cognee_wrap import add as cognee_add
from vismaran_sdk.tensorzero_wrap import inference as tz_inference

# Every write that pertains to a subject must be inside a with_subject() block.
# Embedding writes pick up the subject from the contextvar.
async with with_subject("alice@example.com"):
    await cognee_add(text="...")
    await tz_inference(function_name="chat", input=...)
```

That's the whole contract. If you can't tag a write with a subject, Vismaran cannot guarantee its later erasure — and the SDK will refuse to record provenance, raising `UntracedSubjectError` to make the gap visible early.

## Threat model

See [`docs/architecture/4-threat.mmd`](docs/architecture/4-threat.mmd) for the diagram. Summary of what the receipt provably attests vs. doesn't:

**Attests:** at time T, the named adapters removed all rows whose provenance traced to subject_id from LIVE + PROV stores.

**Does NOT attest:** anything in database backups, off-platform copies (chat transcripts in third-party tools, cached LLM outputs), model weights / fine-tunes that already trained on the subject's data, mirrored observability stacks, third-party log shippers, or — fundamentally — that the operator's signing key isn't compromised. Those need separate controls (retention SLAs on backups, DPIA for fine-tunes, key-transparency log in v0.3+).

## Versioning

- **v0.1** — alpha; APIs may change. Adapters land Days 2–4.
- **v0.2** — crypto-shred mode, anonymize-partial-subject, more graph backends.
- **v0.3** — Mem0 / Zep / Graphiti adapters, Qdrant / Weaviate / Milvus vector adapters, CopilotKit + Langfuse + OpenTelemetry log adapters, TypeScript client.
- **v1.0** — when at least 3 production operators have run Vismaran for a real RTBF and submitted receipts a regulator accepted.

## Non-goals

- A managed cloud erasure service (not in v0.x).
- A frontend UI library — the `examples/fastapi_demo/` is one example; the core is headless.
- Backup deletion (a different problem with different primitives).
- Model unlearning (a research problem; see v0.3+ DPIA guidance).

## Acknowledgements

The hard parts are 95% spec and 5% code. Particular debt to:
- Cognee — for shipping `cognee.forget()` in v1.1.0; the tier-1/tier-2 paths are theirs.
- TensorZero — for the `tags` field on inference + feedback, which makes tier-scoped log deletion tractable.
- pgvector — for being plain, predictable, and not trying to be magic.
