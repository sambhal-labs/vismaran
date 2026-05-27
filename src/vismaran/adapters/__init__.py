"""Adapters package — concrete implementations of the three protocols.

Importing an adapter pulls in its underlying framework dependency, so users
should install only the extras they need:

    uv add vismaran[cognee]
    uv add vismaran[pgvector]
    uv add vismaran[tensorzero]

Or all three at once:

    uv add vismaran[all]
"""

from vismaran.adapters.base import Adapter, GraphAdapter, LogAdapter, VectorAdapter

__all__ = ["Adapter", "GraphAdapter", "LogAdapter", "VectorAdapter"]
