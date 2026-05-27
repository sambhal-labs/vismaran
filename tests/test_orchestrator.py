"""Orchestrator semantics: idempotency, dry-run vs commit, partial-failure.

Lands Day 4 once the orchestrator is real.
"""

import pytest


@pytest.mark.skip(reason="orchestrator stub; Day 4")
def test_dry_run_does_not_mutate() -> None: ...


@pytest.mark.skip(reason="orchestrator stub; Day 4")
def test_commit_emits_signed_receipt() -> None: ...


@pytest.mark.skip(reason="orchestrator stub; Day 4")
def test_partial_failure_does_not_sign_receipt() -> None:
    """Fail-loud contract: ANY adapter failure ⇒ no receipt + PartialErasureError."""


@pytest.mark.skip(reason="orchestrator stub; Day 4")
def test_idempotent_retry_after_failure() -> None: ...
