"""Tests for reading a rendered transcript back into its parts."""

from __future__ import annotations

import pytest

from corpus_query.transcripts.parse import (
    TranscriptError,
    parse_file,
    parse_transcript,
)
from corpus_query.transcripts.render import render_meeting


def test_the_header_fields_come_back(make_meeting):
    meeting = make_meeting()
    parsed = parse_transcript(render_meeting(meeting))
    assert parsed.subject == meeting.subject
    assert parsed.date == meeting.date
    assert parsed.attendees == tuple(meeting.attendees)


def test_the_turns_come_back_in_order(make_meeting):
    meeting = make_meeting()
    parsed = parse_transcript(render_meeting(meeting))
    assert [(turn.speaker, turn.text) for turn in parsed.turns] == [
        (turn.speaker, turn.text) for turn in meeting.turns
    ]


def test_each_turn_keeps_the_line_it_was_read_from(make_meeting):
    rendered = render_meeting(make_meeting())
    parsed = parse_transcript(rendered)
    lines = rendered.splitlines()
    for turn in parsed.turns:
        assert turn.line in lines


def test_an_attendee_who_never_speaks_is_still_an_attendee(make_meeting):
    parsed = parse_transcript(render_meeting(make_meeting()))
    assert "Sofia" in parsed.attendees
    assert "Sofia" not in {turn.speaker for turn in parsed.turns}


def test_a_marker_inside_turn_text_does_not_confuse_the_parser(make_meeting):
    meeting = make_meeting(
        turns=[{"speaker": "Priya", "text": "The log line reads [Marcus]: retry."}]
    )
    parsed = parse_transcript(render_meeting(meeting))
    assert [(turn.speaker, turn.text) for turn in parsed.turns] == [
        ("Priya", "The log line reads [Marcus]: retry.")
    ]


def test_a_file_that_is_not_a_transcript_names_itself_and_what_was_expected(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("Just some notes.\n", encoding="utf-8")
    with pytest.raises(TranscriptError) as caught:
        parse_file(path)
    assert "notes.md" in str(caught.value)
    assert "subject" in str(caught.value)


def test_a_missing_file_is_reported_rather_than_raised_as_an_os_error(tmp_path):
    with pytest.raises(TranscriptError) as caught:
        parse_file(tmp_path / "absent.md")
    assert "absent.md" in str(caught.value)


def test_a_missing_transcript_section_is_an_error(make_meeting):
    rendered = render_meeting(make_meeting())
    without = rendered.replace("## Transcript\n", "")
    with pytest.raises(TranscriptError) as caught:
        parse_transcript(without, source="broken.md")
    assert "broken.md" in str(caught.value)
    assert "## Transcript" in str(caught.value)


def test_a_missing_date_is_an_error(make_meeting):
    rendered = render_meeting(make_meeting())
    without = "\n".join(
        line for line in rendered.splitlines() if not line.startswith("- **Date:**")
    )
    with pytest.raises(TranscriptError) as caught:
        parse_transcript(without, source="broken.md")
    assert "Date" in str(caught.value)


def test_a_date_that_is_not_a_calendar_date_is_an_error(make_meeting):
    rendered = render_meeting(make_meeting()).replace("2026-03-04", "last Tuesday")
    with pytest.raises(TranscriptError) as caught:
        parse_transcript(rendered, source="broken.md")
    assert "last Tuesday" in str(caught.value)


def test_prose_inside_the_transcript_section_is_an_error(make_meeting):
    rendered = render_meeting(make_meeting()).replace(
        "## Transcript\n\n", "## Transcript\n\nThe recording starts here.\n"
    )
    with pytest.raises(TranscriptError) as caught:
        parse_transcript(rendered, source="broken.md")
    assert "not a turn" in str(caught.value)


def test_an_empty_transcript_section_is_an_error(make_meeting):
    rendered = render_meeting(make_meeting())
    start = rendered.index("## Transcript")
    end = rendered.index("## Decisions")
    emptied = rendered[: start + len("## Transcript\n\n")] + rendered[end:]
    with pytest.raises(TranscriptError) as caught:
        parse_transcript(emptied, source="broken.md")
    assert "no turns" in str(caught.value)


def test_parsing_a_file_records_where_it_came_from(tmp_path, make_meeting):
    path = tmp_path / "rev-b-schedule.md"
    path.write_text(render_meeting(make_meeting()), encoding="utf-8")
    assert parse_file(path).source == str(path)
