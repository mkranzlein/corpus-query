"""Fixtures shared by the transcript tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from corpus_query.transcripts.roster import DEFAULT_ROSTER_FILE
from corpus_query.transcripts.schema import Meeting

REPO_ROOT = Path(__file__).resolve().parents[1]

_MEETING: dict[str, Any] = {
    "subject": "Rev B schedule",
    "date": "2026-03-04",
    "length_minutes": 30,
    "attendees": ["Priya", "Marcus", "Sofia"],
    "turns": [
        {"speaker": "Priya", "text": "Where are we on the rev B boards?"},
        {"speaker": "Marcus", "text": "Two weeks out, assuming the connectors land."},
    ],
    "decisions": ["Hold the rev B date and re-check the connector lead time."],
    "action_items": [
        {"assignee": "Marcus", "task": "Confirm the connector lead time with Devon."}
    ],
}


@pytest.fixture
def roster_path() -> Path:
    """Return the committed roster, found without depending on the cwd."""
    return REPO_ROOT / DEFAULT_ROSTER_FILE


@pytest.fixture
def make_meeting() -> Callable[..., Meeting]:
    """Return a factory that builds a valid meeting, with fields overridden.

    Sofia attends without speaking and without owning an action item, so the
    default meeting exercises both of those allowances on its own.
    """

    def factory(**overrides: Any) -> Meeting:
        return Meeting.model_validate(_MEETING | overrides)

    return factory
