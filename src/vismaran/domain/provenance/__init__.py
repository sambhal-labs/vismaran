"""Provenance sub-domain — the ledger record value object.

The ledger *store* (a Postgres implementation) lives in the infrastructure
layer and is reached through the ``ProvenanceStore`` port in
``vismaran.application.ports``.
"""

from vismaran.domain.provenance.record import ProvenanceRecord

__all__ = ["ProvenanceRecord"]
