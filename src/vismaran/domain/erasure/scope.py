"""Erasure value objects: what axis we erase along, and in what mode."""

from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    """Which axis of the data we're erasing along."""

    SUBJECT = "subject"
    DATASET = "dataset"


class Mode(StrEnum):
    """Erasure mode."""

    DRY_RUN = "dry_run"
    COMMIT = "commit"
