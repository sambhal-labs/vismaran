"""Cross-check that tag-key constants stay in sync across modules.

The TensorZero log adapter has its own copy of the tag keys (so the deletion
path doesn't depend on the ingest SDK) and the SDK wrapper has its own copy
(so ingest doesn't depend on the adapter). This test catches drift.
"""

from vismaran.adapters import tensorzero_log
from vismaran_sdk import tag
from vismaran_sdk import tensorzero_wrap


def test_tag_keys_match_across_modules() -> None:
    assert tag.TAG_KEY_SUBJECT == tensorzero_log.TAG_KEY_SUBJECT == tensorzero_wrap.TAG_KEY_SUBJECT
    assert tag.TAG_KEY_TENANT == tensorzero_log.TAG_KEY_TENANT == tensorzero_wrap.TAG_KEY_TENANT
    assert tag.TAG_KEY_POLICY == tensorzero_log.TAG_KEY_POLICY == tensorzero_wrap.TAG_KEY_POLICY


def test_tag_key_uses_vismaran_prefix() -> None:
    """We MUST use the ``vismaran::`` namespace — TensorZero reserves ``tensorzero::``."""
    assert tag.TAG_KEY_SUBJECT.startswith("vismaran::")
    assert not tag.TAG_KEY_SUBJECT.startswith("tensorzero::")
