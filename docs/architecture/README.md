# Vismaran — Architecture

Five diagrams. Each one has a Mermaid source (`.mmd`) and a pre-rendered PNG (`img/v3-*.png`). The PNGs are the canonical visuals shipped in the README and tweets; the Mermaid sources are what you edit when the design changes.

## 1. Component overview

The lay of the land — write path, erase path, memory layers, and where the Provenance Index sits. Agent-framework-agnostic at the protocol level; v0 ships three concrete adapters.

![Component overview](img/v3-1-component.png)

Source: [`1-component.mmd`](1-component.mmd)

## 2. Ingest flow

The provenance contract in one sequence diagram. **One agent write = one provenance row.** Without this, erasure across opaque embeddings is impossible.

![Ingest flow](img/v3-2-ingest.png)

Source: [`2-ingest.mmd`](2-ingest.mmd)

## 3. Erasure flow

Happy path (dry-run → confirm → parallel adapter erase → signed receipt → regulator verifies offline) and the failure path (fail-loud, no partial-commit receipt, idempotent retry).

![Erasure flow](img/v3-3-erasure.png)

Source: [`3-erasure.mmd`](3-erasure.mmd)

## 4. Threat model

What the receipt provably attests (everything inside Vismaran's trust boundary) vs. what it doesn't (backups, off-platform copies, fine-tunes that already trained on the data, mirrored observability, malicious operator). Anything in OUT needs separate controls.

![Threat model](img/v3-4-threat.png)

Source: [`4-threat.mmd`](4-threat.mmd)

## 5. Adapter protocol

The three interfaces (`GraphAdapter`, `VectorAdapter`, `LogAdapter`) and their v0 + roadmap implementations.

![Adapter protocol](img/v3-5-adapter.png)

Source: [`5-adapter.mmd`](5-adapter.mmd)

---

## Regenerating the PNGs

The Mermaid sources are authoritative; the PNGs are checked in for convenience. To regenerate (when you change a `.mmd`):

```bash
# Using the Mermaid CLI (npm install -g @mermaid-js/mermaid-cli):
mmdc -i docs/architecture/1-component.mmd -o docs/architecture/img/v3-1-component.png -b transparent -w 1600

# Or render via mermaid.live and download.
```

When you regenerate, bump the prefix (`v3-*` → `v4-*`) so historical PNGs stay diffable and the README hasn't silently changed.
