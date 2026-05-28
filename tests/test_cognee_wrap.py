"""vismaran_sdk.cognee_wrap tests.

These tests mock ``cognee.add`` directly to verify the wrapper's tag injection
and provenance recording without needing a live Cognee + LLM setup. The full
ingest-via-LLM-then-delete flow is exercised in the Day-6 demo end-to-end test.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

import vismaran_sdk.cognee_wrap as cw
from vismaran.domain import UntracedSubjectError
from vismaran.infrastructure.persistence import ProvenanceIndex
from vismaran_sdk.tag import with_subject

DEFAULT_DSN = "postgres://vismaran:vismarandev@localhost:5432/vismaran"


# --- pure-logic tests (no DB, no Cognee) -----------------------------------


def test_subject_tag_uses_prefix() -> None:
    assert cw._subject_tag("alice@example.com") == "subject::alice@example.com"


def test_extract_record_ids_handles_dataset_list_shape() -> None:
    """Most common Cognee return: list[Dataset(data=list[Data(id=UUID, ...)])]."""

    class Item:
        def __init__(self, _id: str) -> None:
            self.id = _id

    class Ds:
        def __init__(self, items: list[Item]) -> None:
            self.data = items

    ids = cw._extract_record_ids([Ds([Item("a-1"), Item("a-2")]), Ds([Item("b-1")])])
    assert ids == ["a-1", "a-2", "b-1"]


def test_extract_record_ids_handles_empty() -> None:
    assert cw._extract_record_ids(None) == []
    assert cw._extract_record_ids([]) == []


def test_extract_record_ids_handles_single_object_with_id() -> None:
    class Lone:
        def __init__(self) -> None:
            self.id = "lone-1"

    assert cw._extract_record_ids(Lone()) == ["lone-1"]


# --- wrapper behavior (mocked cognee.add) ----------------------------------


async def test_add_raises_untraced_when_no_subject_in_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_add = AsyncMock(return_value=[])
    monkeypatch.setattr(cw.cognee, "add", mock_add)

    with pytest.raises(UntracedSubjectError, match="with_subject"):
        await cw.add("hello world")

    mock_add.assert_not_called()


async def test_add_passes_through_when_fail_loud_false(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_add = AsyncMock(return_value=[])
    monkeypatch.setattr(cw.cognee, "add", mock_add)

    await cw.add("hello world", fail_loud=False)
    mock_add.assert_called_once()
    # No subject in scope ⇒ no subject tag should have been injected.
    call_kwargs = mock_add.call_args.kwargs
    assert call_kwargs.get("node_set") is None


async def test_add_injects_subject_node_set_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_add = AsyncMock(return_value=[])
    monkeypatch.setattr(cw.cognee, "add", mock_add)

    async with with_subject("alice@example.com"):
        await cw.add("Alice lives in Mumbai")

    kwargs = mock_add.call_args.kwargs
    assert kwargs["node_set"] == ["subject::alice@example.com"]
    assert kwargs["dataset_name"] == "main_dataset"


async def test_add_preserves_caller_supplied_node_set_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_add = AsyncMock(return_value=[])
    monkeypatch.setattr(cw.cognee, "add", mock_add)

    async with with_subject("alice@example.com"):
        await cw.add("text", node_set=["topic::geography", "lang::en"])

    tags = mock_add.call_args.kwargs["node_set"]
    assert "topic::geography" in tags
    assert "lang::en" in tags
    assert "subject::alice@example.com" in tags


async def test_add_does_not_duplicate_subject_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the caller already passed our tag explicitly, don't add it twice."""
    mock_add = AsyncMock(return_value=[])
    monkeypatch.setattr(cw.cognee, "add", mock_add)

    async with with_subject("alice@example.com"):
        await cw.add("text", node_set=["subject::alice@example.com"])

    tags = mock_add.call_args.kwargs["node_set"]
    assert tags.count("subject::alice@example.com") == 1


# --- provenance recording (live Postgres) ----------------------------------

pytestmark_integration = pytest.mark.integration


@pytest.fixture
async def provenance() -> AsyncIterator[ProvenanceIndex]:
    idx = await ProvenanceIndex.from_dsn(DEFAULT_DSN)
    async with idx._pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE vismaran.provenance RESTART IDENTITY")
    yield idx
    await idx.close()


@pytest.mark.integration
async def test_add_records_provenance_row_per_data_item(
    monkeypatch: pytest.MonkeyPatch, provenance: ProvenanceIndex
) -> None:
    class Item:
        def __init__(self, _id: str) -> None:
            self.id = _id

    class Ds:
        def __init__(self, items: list[Item]) -> None:
            self.data = items

    fake_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    mock_add = AsyncMock(return_value=[Ds([Item(i) for i in fake_ids])])
    monkeypatch.setattr(cw.cognee, "add", mock_add)

    async with with_subject("alice@example.com"):
        await cw.add("text", provenance=provenance)

    rows = await provenance.lookup_by_framework("alice@example.com", "cognee")
    assert {r.record_id for r in rows} == set(fake_ids)
    assert all(r.tags.get("dataset_name") == "main_dataset" for r in rows)


@pytest.mark.integration
async def test_add_records_fallback_row_when_result_shape_unknown(
    monkeypatch: pytest.MonkeyPatch, provenance: ProvenanceIndex
) -> None:
    """If we can't pull IDs out of the Cognee result, still record SOMETHING."""
    mock_add = AsyncMock(return_value="opaque-string-cognee-returned")
    monkeypatch.setattr(cw.cognee, "add", mock_add)

    async with with_subject("alice@example.com"):
        await cw.add("text", provenance=provenance, dataset_name="custom_ds")

    rows = await provenance.lookup_by_framework("alice@example.com", "cognee")
    assert len(rows) == 1
    assert rows[0].record_id == "dataset:custom_ds"


def test_default_dataset_matches_cognee_default() -> None:
    """If Cognee changes its default dataset name, our default must follow."""
    import inspect

    import cognee

    sig = inspect.signature(cognee.add)
    cognee_default = sig.parameters["dataset_name"].default
    assert cognee_default == cw.DEFAULT_DATASET
