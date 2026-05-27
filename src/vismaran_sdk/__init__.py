"""Vismaran SDK — the provenance contract.

``vismaran_sdk`` is the ingest-side library: thin wrappers around the agent
frameworks Vismaran supports that (a) propagate a subject identifier through
the framework's native tagging mechanism and (b) record one row in the
Vismaran provenance index per write.

Without provenance, erasure across opaque rows (especially embeddings) is
impossible. The SDK is what makes the right-to-be-forgotten cashable.
"""

from vismaran_sdk.tag import (
    TAG_KEY_POLICY,
    TAG_KEY_SUBJECT,
    TAG_KEY_TENANT,
    current_subject,
    tag_subject,
    with_subject,
)

__all__ = [
    "TAG_KEY_POLICY",
    "TAG_KEY_SUBJECT",
    "TAG_KEY_TENANT",
    "current_subject",
    "tag_subject",
    "with_subject",
]
