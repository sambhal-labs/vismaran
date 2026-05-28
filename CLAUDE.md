# CLAUDE.md

Guidance for any agent or contributor working in this repository.

## What this is

**Vismaran** (विस्मरण — Sanskrit/Hindi for *forgetting*) is provable
right-to-be-forgotten infrastructure for AI agent memory: DPDP / GDPR Article 17
erasure across the three layers an agent remembers a person in — graph (Cognee),
vector (pgvector), and inference log (TensorZero) — emitting an Ed25519-signed
deletion receipt a regulator can verify offline.

The library is **headless**. `examples/` apps are illustrative only; never make
the core depend on them.

## Golden rules

- **Conventional Commits.** `feat:`, `fix:`, `refactor:`, `test:`, `docs:`,
  `chore:`, `ci:`, `perf:`, with optional scope (`feat(graph): ...`). Imperative
  subject ≤ 72 chars; body explains the *why*. No sprint-day ("Day 2") subjects.
- **No `Co-Authored-By: Claude` trailers.** This repo's history reads as a single
  authored project.
- **Commit identity is `sambhal-labs`.** Git config is already set globally on
  this machine (`255515429+sambhal-labs@users.noreply.github.com`). Just
  `git commit` — no `-c` overrides. Verify with
  `gh api repos/sambhal-labs/vismaran/commits/HEAD --jq .author.login`.
- **Never commit to `main`.** Feature branch (`feat/*`, `fix/*`, `refactor/*`,
  `test/*`, `chore/*`, `ci/*`) → PR → **squash merge**. `main` is protected.
- **TDD.** Write the failing test first, watch it fail, then implement to green.
  PRs that add behavior without a test that would have failed before are
  incomplete.
- **Integration tests hit real services.** No mocks for the Postgres / Neo4j /
  ClickHouse / TensorZero layers — a compliance tool that passes against mocks
  and fails against the real store is worse than no tool. The only sanctioned
  mock is `cognee.add` in unit tests (avoids needing an LLM for entity
  extraction); the full ingest path is covered by integration tests.

## Architecture (current — flat; layered DDD refactor in progress)

```
src/vismaran/                 # the headless core (Python package: vismaran)
  types.py                    # SubjectId, Scope, Mode, PerStoreResult, ProvenanceRow
  exceptions.py               # VismaranError hierarchy
  orchestrator.py             # Orchestrator — fans out to adapters, signs receipt
  receipt.py                  # Receipt value object + Ed25519 sign/verify (Day 5)
  provenance.py               # ProvenanceIndex — asyncpg ledger
  cli.py                      # `vismaran` CLI (erase / verify / keygen)
  adapters/
    base.py                   # GraphAdapter / VectorAdapter / LogAdapter Protocols (the ports)
    cognee_graph.py           # CogneeGraphAdapter
    pgvector_vector.py        # PgvectorVectorAdapter (Day 3)
    tensorzero_log.py         # TensorZeroLogAdapter (Day 4)
src/vismaran_sdk/             # ingest-side bounded context (the provenance contract)
  tag.py                      # with_subject contextvar, tag_subject decorator
  cognee_wrap.py              # cognee.add wrapper: tag + record provenance
  tensorzero_wrap.py          # TZ inference/feedback wrapper (Day 4)
tests/                        # pytest; integration tests marked @pytest.mark.integration
docker/                       # docker-compose service config + Postgres init SQL
docs/architecture/            # 5 Mermaid sources + rendered PNGs
examples/fastapi_demo/        # illustrative demo (Day 6) — NOT a core dependency
```

The adapter Protocols in `adapters/base.py` are hexagonal **ports**; concrete
adapters are the driven side. The orchestrator depends only on the Protocols.

## The provenance contract

You can't erase what you didn't trace. Every subject-bearing write must go
through `vismaran_sdk` inside a `with_subject(...)` block, which (a) propagates
the subject via a contextvar and (b) records a row in the provenance index.

- Tag key is **`vismaran::subject_id`** — namespaced because TensorZero reserves
  `tensorzero::`. The constant is duplicated in `vismaran_sdk.tag`,
  `vismaran_sdk.tensorzero_wrap`, and `adapters/tensorzero_log` so neither side
  depends on the other; `tests/test_tag.py` cross-checks they never drift.
- Cognee uses a NodeSet tag `subject::<id>` (the `belongs_to_set` array property)
  rather than the TZ-style tag map. The prefix is shared between
  `vismaran_sdk.cognee_wrap` and `adapters/cognee_graph` and is also drift-tested.

## Commands

```bash
make install      # uv sync --extra all --extra demo --extra dev
make up           # docker compose up -d (neo4j + postgres+pgvector + clickhouse + tensorzero)
make down         # tear the stack down
make test         # full suite (needs `make up` for integration tests)
make test-unit    # unit only: pytest -m "not integration" (no docker needed)
make lint         # ruff check .
make typecheck    # pyright
make seed         # seed Alice/Bob/Carol across all 3 layers (Day 6)
make demo         # run the FastAPI+HTMX demo (Day 6)
```

Run a single test: `uv run pytest tests/test_cognee_adapter.py -v`.

## Testing conventions

- `@pytest.mark.integration` ⇒ needs the docker stack. CI runs these against
  service containers; locally run `make up` first.
- Integration fixtures truncate/clean their own state and use random-suffixed
  subject IDs so concurrent runs don't collide.
- `asyncio_mode = auto` (pytest-asyncio) — `async def test_*` just works.

## Sprint context

7-day build-in-public sprint started 2026-05-27. Adapters land graph (done) →
vector → log → receipt → demo. The internal day-by-day plan is not part of the
repo; commit messages and PRs describe changes by what they do, not which sprint
day produced them.
