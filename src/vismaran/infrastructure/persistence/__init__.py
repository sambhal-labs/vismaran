"""Persistence — the Postgres-backed provenance ledger (implements ``ProvenanceStore``)."""

from vismaran.infrastructure.persistence.provenance_pg import ProvenanceIndex

__all__ = ["ProvenanceIndex"]
