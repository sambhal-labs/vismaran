"""TensorZeroLogAdapter integration tests — hit live ClickHouse + TZ gateway.

Lands Day 4. The model_inference_cascade test is the canary for the most
common implementation bug (forgetting the inference_id join leaves raw
provider request/response bodies in ClickHouse forever).
"""

import pytest


@pytest.mark.integration
@pytest.mark.skip(reason="TensorZeroLogAdapter stub; Day 4")
def test_erase_deletes_tag_scoped_rows() -> None: ...


@pytest.mark.integration
@pytest.mark.skip(reason="TensorZeroLogAdapter stub; Day 4")
def test_model_inference_cascade_by_inference_id() -> None:
    """ModelInference has no tags column. MUST cascade via inference_id."""


@pytest.mark.integration
@pytest.mark.skip(reason="TensorZeroLogAdapter stub; Day 4")
def test_feedback_tagged_independently_of_inference() -> None:
    """TZ does not propagate tags from inference to feedback — wrapper must inject on both."""


@pytest.mark.integration
@pytest.mark.skip(reason="TensorZeroLogAdapter stub; Day 4")
def test_pre_mutation_count_matches_receipt() -> None: ...
