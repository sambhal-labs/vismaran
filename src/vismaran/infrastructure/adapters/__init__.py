"""Concrete store adapters — the driven side of the adapter ports.

Importing an adapter pulls in its underlying framework dependency, so install
only the extras you need:

    uv add vismaran[cognee]      # CogneeGraphAdapter
    uv add vismaran[pgvector]    # PgvectorVectorAdapter
    uv add vismaran[tensorzero]  # TensorZeroLogAdapter
    uv add vismaran[all]         # all three
"""

from vismaran.infrastructure.adapters.cognee_graph import CogneeGraphAdapter
from vismaran.infrastructure.adapters.pgvector_vector import PgvectorVectorAdapter
from vismaran.infrastructure.adapters.tensorzero_log import TensorZeroLogAdapter

__all__ = ["CogneeGraphAdapter", "PgvectorVectorAdapter", "TensorZeroLogAdapter"]
