"""PgvectorVectorAdapter integration tests — hit live Postgres+pgvector.

Implemented with the vector-adapter milestone.
"""

import pytest


@pytest.mark.integration
@pytest.mark.skip(reason="PgvectorVectorAdapter stub — vector-adapter milestone")
def test_erase_deletes_only_subject_embeddings() -> None: ...


@pytest.mark.integration
@pytest.mark.skip(reason="PgvectorVectorAdapter stub — vector-adapter milestone")
def test_erase_without_provenance_raises_untraced() -> None: ...
