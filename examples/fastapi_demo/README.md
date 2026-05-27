# Vismaran demo — FastAPI + HTMX

A self-contained example: a tiny LangGraph chat agent whose memory lives in
Cognee + pgvector + TensorZero, with a `vismaran_erase` tool the agent calls
when a user invokes their right to be forgotten. The frontend is
server-rendered Jinja with HTMX swaps — no Node, no JS framework.

This is **not** part of the Vismaran core. The core is headless. This is one
example of what plugging Vismaran in looks like.

## Run

```bash
# from repo root
docker compose up -d
uv sync --extra demo

make seed   # plant Alice, Bob, Carol across all three layers
make demo   # http://localhost:8000
```

## What the demo shows

1. **Ingest.** User chats with the agent → Cognee writes graph nodes; pgvector stores embeddings; TensorZero logs every inference (and any thumbs-up/down feedback). All three writes carry `vismaran::subject_id` tags via `vismaran_sdk`.
2. **Preview.** User says "delete everything you know about me" → agent calls `vismaran_erase(subject=..., dry_run=True)` → HTMX swaps in a preview card listing per-layer counts.
3. **Confirm.** Click → real erasure runs in parallel across the three adapters → signed receipt JSON streams back into the page.
4. **Re-query.** Agent re-asked "what do you know about Alice?" → answers "nothing."
5. **Verify.** `uv run vismaran verify receipt.json` returns OK; tamper any field, returns FAIL.

## Files

- [`backend/app.py`](backend/app.py) — FastAPI app, routes, HTMX endpoints.
- [`backend/agent.py`](backend/agent.py) — LangGraph chat agent. Uses Cognee + pgvector + TensorZero.
- [`backend/erase_tool.py`](backend/erase_tool.py) — the agent's `vismaran_erase` tool (human-in-the-loop confirmation).
- [`backend/seed.py`](backend/seed.py) — seeds Alice/Bob/Carol via `vismaran_sdk` wrappers.
- [`backend/templates/`](backend/templates/) — Jinja templates for the chat UI + erase preview card.

Lands Day 6.
