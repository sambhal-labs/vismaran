"""Erasure sub-domain — the core: scopes, modes, and per-store results."""

from vismaran.domain.erasure.results import AdapterKind, PerStoreResult
from vismaran.domain.erasure.scope import Mode, Scope

__all__ = ["AdapterKind", "Mode", "PerStoreResult", "Scope"]
