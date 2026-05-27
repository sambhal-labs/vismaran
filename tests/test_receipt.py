"""Receipt: canonical JSON, Ed25519 sign / verify, tampering rejection.

Lands Day 5.
"""

import pytest


@pytest.mark.skip(reason="receipt stub; Day 5")
def test_sign_then_verify_roundtrip() -> None: ...


@pytest.mark.skip(reason="receipt stub; Day 5")
def test_tampered_field_fails_verify() -> None: ...


@pytest.mark.skip(reason="receipt stub; Day 5")
def test_subject_id_never_appears_raw() -> None:
    """Receipts hold only the hashed subject_id — raw must NEVER leak."""


@pytest.mark.skip(reason="receipt stub; Day 5")
def test_constant_time_verify() -> None: ...
