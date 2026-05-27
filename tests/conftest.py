"""Shared pytest fixtures.

Integration fixtures (``pg_pool``, ``ch_client``, ``neo4j_driver``,
``tz_client``) assume ``make up`` is running; tests that use them are tagged
``@pytest.mark.integration`` so ``pytest -m "not integration"`` works on a
laptop without docker.

Lands Day 2–4 as each adapter materializes.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def alice_subject() -> str:
    return "alice@example.com"


@pytest.fixture
def operator_salt() -> bytes:
    """32-byte deterministic salt for receipt tests. NOT a real deployment salt."""
    return b"vismaran-test-salt-for-fixtures!"
