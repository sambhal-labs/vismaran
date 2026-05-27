"""CogneeGraphAdapter integration tests — hit live Cognee + Neo4j containers.

Tagged ``integration`` so they're skipped in CI/laptop unit runs unless docker
is up.

Lands Day 2.
"""

import pytest


@pytest.mark.integration
@pytest.mark.skip(reason="CogneeGraphAdapter stub; Day 2")
def test_tier1_user_scope_uses_cognee_forget() -> None:
    """Subject IS a Cognee user ⇒ forget(everything=True, user=...) path."""


@pytest.mark.integration
@pytest.mark.skip(reason="CogneeGraphAdapter stub; Day 2")
def test_tier2_dataset_scope_uses_cognee_forget() -> None: ...


@pytest.mark.integration
@pytest.mark.skip(reason="CogneeGraphAdapter stub; Day 2")
def test_tier3_content_scope_uses_cypher_fallback() -> None:
    """Subject mentioned inside content ⇒ Cypher against __Node__ + re-embed."""


@pytest.mark.integration
@pytest.mark.skip(reason="CogneeGraphAdapter stub; Day 2")
def test_preview_does_not_mutate() -> None: ...
