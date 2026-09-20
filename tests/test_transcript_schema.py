"""Tests for the meeting schema."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from corpus_query.transcripts.roster import first_names, read_roster
from corpus_query.transcripts.schema import Meeting, Meetings, normalize_line


def test_a_meeting_carries_the_six_things_that_describe_it(make_meeting):
    meeting = make_meeting()
    assert meeting.subject == "Rev B schedule"
    assert meeting.date == "2026-03-04"
    assert meeting.attendees == ["Priya", "Marcus", "Sofia"]
    assert [turn.speaker for turn in meeting.turns] == ["Priya", "Marcus"]
    assert meeting.turns[0].text == "Where are we on the rev B boards?"
    assert meeting.decisions == [
        "Hold the rev B date and re-check the connector lead time."
    ]
    assert meeting.action_items[0].assignee == "Marcus"
    assert meeting.action_items[0].task.startswith("Confirm")


def test_attendees_are_first_names_from_the_roster(make_meeting, roster_path):
    roster = set(first_names(read_roster(roster_path)))
    meeting = make_meeting()
    assert set(meeting.attendees) <= roster
    assert {turn.speaker for turn in meeting.turns} <= roster
    assert {item.assignee for item in meeting.action_items} <= roster


def test_an_attendee_may_never_speak_and_may_owe_nothing(make_meeting):
    meeting = make_meeting()
    speakers = {turn.speaker for turn in meeting.turns}
    assignees = {item.assignee for item in meeting.action_items}
    assert "Sofia" in meeting.attendees
    assert "Sofia" not in speakers
    assert "Sofia" not in assignees


def test_a_meeting_may_settle_nothing_and_leave_nobody_owing(make_meeting):
    meeting = make_meeting(decisions=[], action_items=[])
    assert meeting.decisions == []
    assert meeting.action_items == []


def test_turn_text_is_flattened_onto_one_line(make_meeting):
    meeting = make_meeting(
        turns=[{"speaker": "Sofia", "text": " First thought.\n\nSecond   thought. "}]
    )
    assert meeting.turns[0].text == "First thought. Second thought."


def test_normalize_line_collapses_every_kind_of_whitespace():
    assert normalize_line("a\r\nb\tc  d\n") == "a b c d"


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject": "   "},
        {"date": "March 4, 2026"},
        {"date": "2026-02-30"},
        {"attendees": []},
        {"attendees": ["Priya", "Priya"]},
        {"attendees": ["Pri]ya"]},
        {"turns": []},
        {"turns": [{"speaker": "", "text": "Something."}]},
        {"turns": [{"speaker": "Pri]ya", "text": "Something."}]},
        {"turns": [{"speaker": "Priya", "text": "  \n "}]},
        {"decisions": ["Fine.", " "]},
        {"action_items": [{"assignee": " ", "task": "Something."}]},
        {"action_items": [{"assignee": "Marcus", "task": ""}]},
    ],
)
def test_unusable_meetings_are_rejected(make_meeting, overrides):
    with pytest.raises(ValidationError):
        make_meeting(**overrides)


def test_the_meetings_alias_names_a_list_of_meetings(make_meeting):
    meeting = make_meeting()
    meetings = TypeAdapter(Meetings).validate_python([meeting.model_dump()])
    assert meetings == [meeting]
    assert all(isinstance(item, Meeting) for item in meetings)
