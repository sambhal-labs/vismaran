"""Vismaran infrastructure layer — concrete adapters, persistence, and crypto.

Everything that touches the outside world (Neo4j, Postgres, ClickHouse,
TensorZero, Ed25519 keys) lives here and implements a port defined in
``vismaran.application.ports``.
"""
