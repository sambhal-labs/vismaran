# Vismaran

> **विस्मरण** (Sanskrit / Hindi: *forgetting*, *oblivion*)
>
> Provable right-to-be-forgotten for AI agent memory — graph, vector, and inference log — with a signed deletion receipt a regulator can verify offline.

[![Status](https://img.shields.io/badge/status-v0.1%20alpha%20%E2%80%94%20Day%201-orange.svg)](#status) [![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.12%2B-3776ab.svg)](pyproject.toml)

## Why this exists

India's **DPDP Rules** take full effect **13 May 2027** (no grace period). GDPR **Article 17** is the parallel global obligation. Both require, in plain language: a user can demand to be forgotten, you have a clock to do it, the obligation extends to your processors, and you must keep a record proving you did.

A production AI agent's memory of a single person isn't in one place — it's smeared across **three layers**:

- **Graph** — structured knowledge-graph memory (entities, relationships, claims). v0 targets [Cognee](https://github.com/topoteretes/cognee) (fronts Neo4j / Kuzu / FalkorDB).
- **Vector** — embeddings whose source text mentions the subject. v0 targets [pgvector](https://github.com/pgvector/pgvector).
- **Log** — the inference + feedback log a self-improvement loop trains on. v0 targets [TensorZero](https://github.com/tensorzero/tensorzero) (fronts ClickHouse).

Honoring an Article 17 request means erasing across **all three**, and proving you did. Nobody has built a clean OSS solution. Vismaran is that solution.

## Status

**v0.1 alpha, Day 1 of a 7-day build sprint (started 2026-05-27).** Right now this repo is the scaffold and the spec. Adapter implementations land Days 2–5. End-to-end demo lands Day 6. Pinned launch happens Day 7.

| Capability | v0.1 (this week) | Roadmap |
|---|:-:|:-:|
| Cognee graph adapter (3-tier: user-scope, dataset-scope, Cypher fallback against `__Node__`) | ⏳ Day 2 | |
| pgvector vector adapter (lineage-driven via provenance index) | ⏳ Day 3 | |
| TensorZero log adapter (7 ClickHouse tables, ModelInference cascade by `inference_id`) | ⏳ Day 4 | |
| Provenance SDK (`vismaran_sdk` — Cognee + TZ wrappers) | ⏳ Day 1–4 | |
| Dry-run preview | ⏳ Day 4 | |
| Signed receipt (Ed25519, JSON, canonical manifest) + `vismaran verify` CLI | ⏳ Day 5 | |
| Idempotent re-runs | ⏳ Day 4 | |
| Fail-loud partial erasure | ⏳ Day 4 | |
| FastAPI + HTMX demo (Cognee + pgvector + TensorZero) | ⏳ Day 6 | |
| Crypto-shred mode | | v0.2 |
| Anonymize-partial-subject (graph) — re-embed redacted chunks | ⚠️ stub | v0.2 |
| Kuzu / FalkorDB / Neptune graph backends | | v0.2 |
| Mem0 / Zep / Graphiti / Letta adapters | | v0.3 |
| Qdrant / Weaviate / Milvus vector | | v0.3 |
| CopilotKit / Langfuse / OpenTelemetry log adapters | | v0.3 |
| TypeScript client | | v0.3 |
| Hosted Vismaran | | TBD |
| Backup-erasure | | non-v0 |

Honest about scope: **both Cognee and TensorZero have zero open GDPR/RTBF issues today** (verified 2026-05-27). Vismaran exists because that gap is real.

## Architecture

Five diagrams (Mermaid source + PNG): see [`docs/architecture/`](docs/architecture/).

- [Component overview](docs/architecture/1-component.mmd) — what plugs into what
- [Ingest flow](docs/architecture/2-ingest.mmd) — the provenance contract
- [Erasure flow](docs/architecture/3-erasure.mmd) — happy + failure branches + regulator verify
- [Threat model](docs/architecture/4-threat.mmd) — what the receipt provably attests to (and what it doesn't)
- [Adapter protocol](docs/architecture/5-adapter.mmd) — Graph / Vector / Log interfaces + v0 vs roadmap impls

See [`SPEC.md`](SPEC.md) for the full design + DPDP / GDPR Article 17 clause mapping.

## Quickstart (will work end-of-Day-7)

```bash
# clone
git clone https://github.com/sambhal-labs/vismaran && cd vismaran

# bring up the stack: neo4j + postgres+pgvector + clickhouse + tensorzero gateway
docker compose up -d

# install + seed Alice/Bob/Carol across all 3 layers
uv sync --extra all --extra demo
make seed

# preview what would be erased
uv run vismaran erase --subject alice@example.com --dry-run

# do it for real → writes receipt.json
uv run vismaran erase --subject alice@example.com

# verify the receipt offline (regulator-grade proof)
uv run vismaran verify receipt.json
```

Today (Day 1) only the scaffold + spec exists; `uv run vismaran` will print "not implemented yet" until Day 5.

## Provenance contract (the only thing your agent has to do)

You can't erase what you didn't trace. Vismaran's SDK gives you 1-line drop-in wrappers:

```python
from vismaran_sdk.tag import with_subject
from vismaran_sdk.cognee_wrap import add as cognee_add
from vismaran_sdk.tensorzero_wrap import inference as tz_inference

async with with_subject("alice@example.com"):
    await cognee_add(text="...")             # tags + records provenance
    await tz_inference(function_name="chat", input=...)  # tags inference with vismaran::subject_id
```

The tag prefix `vismaran::` is namespaced specifically because TensorZero reserves `tensorzero::` — see [`docs/architecture/`](docs/architecture/).

## Project

- **License:** Apache-2.0
- **Built by:** [Manish Pande](https://manishpande.in) — AI Platform Leader, ex-DGM Jio, now independent. ([X: @daodevo8](https://x.com/daodevo8))
- **Build-in-public on X.** Day 1 thesis tweet links here.

## Discussion welcome

- "Why do you need *another* memory tool?" — Open an issue. Short answer: this isn't memory tooling, it's compliance-grade erasure infrastructure. We don't store your data; we erase from where you do.
- "When is the [Mem0 / Zep / Graphiti / Qdrant / your-framework] adapter landing?" — Track [`Adapter requests`](https://github.com/sambhal-labs/vismaran/discussions) (after the launch).
- "Will Vismaran ever be hosted?" — TBD. v0 is OSS-only. We'll let inbound demand decide.
