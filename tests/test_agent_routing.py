"""Tests for turning an abstention into a suggestion of who to ask.

What the graph does with a suggestion is tested in
``tests/test_agent_answer.py``, against the real endpoint. What is under test
here is the part that has no model in it: who the retrieved passages name,
how those names are ranked and resolved, and how the routing model's reply is
read.

Nothing here loads a model or reaches Ollama.
"""

from __future__ import annotations

from typing import Any

import pytest

from corpus_query.agent.routing import (
    MAX_CANDIDATES,
    candidates,
    drafted_question,
    people_named,
    suggestion,
)
from corpus_query.transcripts.roster import Person

ROSTER = (
    Person(first_name="Priya", role="CEO", department="Executive"),
    Person(
        first_name="Marcus",
        role="Head of Hardware Engineering",
        department="Engineering",
    ),
    Person(first_name="Sofia", role="Firmware Engineer", department="Engineering"),
    Person(first_name="Devon", role="Manufacturing Engineer", department="Operations"),
)


def a_citation(
    chunk_id: int = 1,
    author: str | None = None,
    attendees: list[str] | None = None,
    location: str = "turns 0-1",
) -> dict[str, Any]:
    """Build one citation, as the retrieval tool hands them back."""
    return {
        "chunk_id": chunk_id,
        "document_slug": "rev-b-schedule",
        "source_kind": "transcript",
        "title": "Rev B schedule",
        "document_date": "2026-03-04",
        "author": author,
        "attendees": attendees or [],
        "location": location,
    }


def test_a_document_names_its_author() -> None:
    """A passage out of an authored document points at one person."""
    assert people_named(a_citation(author="Devon")) == ["Devon"]


def test_a_meeting_names_everyone_who_was_in_the_room() -> None:
    """A transcript has attendees where a document has an author."""
    assert people_named(a_citation(attendees=["Priya", "Marcus"])) == [
        "Priya",
        "Marcus",
    ]


def test_an_author_stands_for_the_passage_on_its_own() -> None:
    """A passage that has both is attributed to whoever wrote it."""
    assert people_named(a_citation(author="Devon", attendees=["Priya"])) == ["Devon"]


def test_a_passage_that_names_nobody_points_nowhere() -> None:
    """Neither an author nor attendees is not a candidate."""
    assert people_named(a_citation()) == []


def test_candidates_rank_by_how_much_of_the_material_they_own() -> None:
    """Whoever wrote or attended more of what matched comes first."""
    ranked = candidates(
        [
            a_citation(chunk_id=1, attendees=["Priya", "Marcus"]),
            a_citation(chunk_id=2, author="Marcus"),
            a_citation(chunk_id=3, author="Marcus"),
        ],
        roster=ROSTER,
    )

    assert [candidate.person.first_name for candidate in ranked] == ["Marcus", "Priya"]
    assert [len(candidate.evidence) for candidate in ranked] == [3, 1]


def test_a_tie_goes_to_the_better_ranked_passage() -> None:
    """Citations arrive best first, and a tie keeps that order."""
    ranked = candidates(
        [
            a_citation(chunk_id=1, attendees=["Sofia"]),
            a_citation(chunk_id=2, attendees=["Devon"]),
        ],
        roster=ROSTER,
    )
    assert [candidate.person.first_name for candidate in ranked] == ["Sofia", "Devon"]


def test_a_candidate_carries_the_passages_that_named_them() -> None:
    """The why is the citation itself, not a paraphrase of it."""
    matched = a_citation(chunk_id=4, author="Devon", location="Scope > Tolerances")
    [candidate] = candidates([matched], roster=ROSTER)

    assert candidate.evidence == [matched]
    assert candidate.as_dict() == {
        "name": "Devon",
        "role": "Manufacturing Engineer",
        "department": "Operations",
        "passages": 1,
        "evidence": [matched],
    }


def test_a_name_not_on_the_roster_is_dropped() -> None:
    """A string out of a file's properties is not a person to ask."""
    ranked = candidates(
        [a_citation(author="wm-scanner-01"), a_citation(chunk_id=2, author="devon")],
        roster=ROSTER,
    )
    # Matched without regard to case, and spelled the way the roster does.
    assert [candidate.person.first_name for candidate in ranked] == ["Devon"]


def test_a_suggestion_names_a_few_people_rather_than_the_company() -> None:
    """A meeting puts everyone in the room on every passage it produced."""
    ranked = candidates(
        [a_citation(attendees=["Priya", "Marcus", "Sofia", "Devon"])], roster=ROSTER
    )
    assert len(ranked) == MAX_CANDIDATES


def test_nothing_retrieved_is_nobody_to_ask() -> None:
    """No passages, no names, no suggestion."""
    assert candidates([], roster=ROSTER) == []


@pytest.mark.parametrize(
    "reply", ["ANSWERED", "  ANSWERED  ", "answered.", "**ANSWERED**", ""]
)
def test_an_answered_question_drafts_nothing(reply: str) -> None:
    """The sentinel is read through the punctuation a small model adds."""
    assert drafted_question(reply) is None


def test_a_drafted_question_comes_back_as_written() -> None:
    """What the model wrote is what the user is handed to edit."""
    draft = (
        "I was looking for the rev B connector tolerance and the record does "
        "not give a figure. What did we settle on?"
    )
    assert drafted_question(draft) == draft


def test_a_suggestion_needs_somebody_to_suggest() -> None:
    """A draft with no candidates behind it is not returned."""
    assert (
        suggestion(
            [a_citation(author="wm-scanner-01")],
            "What did we settle on?",
            roster=ROSTER,
        )
        is None
    )


def test_a_suggestion_is_plain_data() -> None:
    """Graph state is checkpointed, so what travels in it is dicts."""
    routed = suggestion(
        [a_citation(attendees=["Priya"])], "What did we settle on?", roster=ROSTER
    )
    assert routed == {
        "candidates": [
            {
                "name": "Priya",
                "role": "CEO",
                "department": "Executive",
                "passages": 1,
                "evidence": [a_citation(attendees=["Priya"])],
            }
        ],
        "question": "What did we settle on?",
    }
