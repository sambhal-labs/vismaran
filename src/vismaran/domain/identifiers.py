"""Shared domain identifiers.

These are the vocabulary every sub-domain (erasure, provenance, receipt) uses
to refer to a data subject and a stored record. Pure types — no I/O.
"""

from __future__ import annotations

from typing import NewType

SubjectId = NewType("SubjectId", str)
"""Stable subject identifier the operator chose at ingest time.

Conventionally an email or phone number, but Vismaran treats it as an opaque
string. It is hashed before it leaves the local process (see ``Receipt``).
"""

RecordId = NewType("RecordId", str)
"""Framework-native row identifier (e.g., a Cognee node UUID, a pgvector row
UUID, a TensorZero inference UUIDv7)."""
