"""FastAPI app for the Vismaran demo.

Lands Day 6.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Vismaran demo", version="0.1.0a0")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "Day 1 scaffold — demo backend lands Day 6",
        "spec": "https://github.com/sambhal-labs/vismaran/blob/main/SPEC.md",
    }
