# Contributing to Vismaran

Thanks for considering a contribution. Vismaran is compliance-grade
infrastructure, so the bar for correctness is high — but the contribution
process is ordinary.

## Development setup

```bash
git clone https://github.com/sambhal-labs/vismaran && cd vismaran
make up          # docker compose: neo4j + postgres+pgvector + clickhouse + tensorzero
make install     # uv sync --extra all --extra demo --extra dev
make test        # full suite (unit + integration)
```

Requires: Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), Docker + Compose.

## Workflow

We use **GitHub Flow with squash merges**:

1. Branch off `main`: `feat/…`, `fix/…`, `refactor/…`, `test/…`, `docs/…`,
   `chore/…`, `ci/…`.
2. Open a PR. CI (lint, type-check, unit + integration tests) must pass.
3. A maintainer squash-merges. `main` is protected — no direct pushes.

## Test-Driven Development

Write the failing test first, then the implementation. A PR that adds behavior
should include a test that would have failed before the change. We keep two
tiers:

- **Unit** (`pytest -m "not integration"`) — pure logic, no I/O. Runs anywhere.
- **Integration** (`@pytest.mark.integration`) — hits the real Postgres / Neo4j /
  ClickHouse / TensorZero containers. **No mocks for the storage layers.** A
  compliance tool that passes against mocks but fails against the real store is
  worse than nothing.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat(graph): add Kuzu backend to the Cognee adapter
fix(log): cascade ModelInference deletion by inference_id
refactor: extract Ed25519 signer into infrastructure.crypto
test(vector): cover provenance-miss path for pgvector erase
docs: document the receipt verification flow
```

Subject in the imperative mood, ≤ 72 chars. Body explains *why*, not *what*.

## Code style

- `ruff` for lint + format (`make lint`, `uv run ruff format .`).
- `pyright` in standard mode (`make typecheck`). New code is fully typed.
- Public APIs get docstrings; internal helpers get them only when the *why* is
  non-obvious.

## Adapter contributions

New store adapters are very welcome — see the roadmap in [`README.md`](README.md).
An adapter implements one of the `GraphAdapter` / `VectorAdapter` / `LogAdapter`
Protocols in [`src/vismaran/adapters/base.py`](src/vismaran/adapters/base.py) and
ships with integration tests against a real instance of that store. Open a
discussion first if you want to coordinate.

## Reporting security issues

Do not open a public issue for vulnerabilities. See
[`SECURITY.md`](SECURITY.md).
