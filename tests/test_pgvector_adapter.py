"""PgvectorVectorAdapter integration tests — hit live Postgres+pgvector.

Lands Day 3.
"""

import pytest


@pytest.mark.integration
@pytest.mark.skip(reason="PgvectorVectorAdapter stub; Day 3")
def test_erase_deletes_only_subject_embeddings() -> None: ...


@pytest.mark.integration
@pytest.mark.skip(reason="PgvectorVectorAdapter stub; Day 3")
def test_erase_without_provenance_raises_untraced() -> None: ...
