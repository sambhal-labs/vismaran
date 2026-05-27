"""The agent's ``vismaran_erase`` tool.

Always dry-runs first, surfaces the preview card via HTMX, waits for the user
to confirm, then calls the orchestrator. NEVER auto-commits — this is a
destructive tool exposed to an LLM, and the pattern requires human-in-the-loop.

Lands Day 6.
"""
