"""Tests for the markdown renderer."""

from __future__ import annotations

import re

from corpus_query.transcripts.render import EMPTY_SECTION, render_meeting

SPEAKER_MARKER = re.compile(r"^\[([^\]]+)\]: (.*)$")


def parse_turns(markdown: str) -> list[tuple[str, str]]:
    """Read speakers and turn text back out of a rendered transcript.

    This lives in the test rather than in the package on purpose: it exists to
    show the rendered format is unambiguous, not to be used by anything.

    Args:
        markdown: A rendered meeting.

    Returns:
        One ``(speaker, text)`` pair per turn, in transcript order.
    """
    lines = markdown.splitlines()
    start = lines.index("## Transcript") + 1
    end = lines.index("## Decisions")
    matches = (SPEAKER_MARKER.match(line) for line in lines[start:end])
    return [(m.group(1), m.group(2)) for m in matches if m]


def test_the_four_sections_appear_in_order(make_meeting):
    rendered = render_meeting(make_meeting())
    headings = [line for line in rendered.splitlines() if line.startswith("#")]
    assert headings == [
        "# Rev B schedule",
        "## Transcript",
        "## Decisions",
        "## Action items",
    ]


def test_the_header_carries_subject_date_and_attendees(make_meeting):
    rendered = render_meeting(make_meeting())
    assert rendered.startswith("# Rev B schedule\n")
    assert "- **Date:** 2026-03-04" in rendered
    assert "- **Attendees:** Priya, Marcus, Sofia" in rendered


def test_each_turn_is_one_line_with_the_marker_at_its_start(make_meeting):
    rendered = render_meeting(make_meeting())
    assert "[Priya]: Where are we on the rev B boards?" in rendered.splitlines()


def test_a_turn_cannot_span_lines(make_meeting):
    meeting = make_meeting(
        turns=[{"speaker": "Sofia", "text": "First thought.\n\nSecond thought."}]
    )
    assert parse_turns(render_meeting(meeting)) == [
        ("Sofia", "First thought. Second thought.")
    ]


def test_decisions_and_action_items_render_as_bulleted_lists(make_meeting):
    lines = render_meeting(make_meeting()).splitlines()
    assert "- Hold the rev B date and re-check the connector lead time." in lines
    assert "- **Marcus:** Confirm the connector lead time with Devon." in lines


def test_empty_sections_say_so(make_meeting):
    rendered = render_meeting(make_meeting(decisions=[], action_items=[]))
    assert rendered.count(EMPTY_SECTION) == 2


def test_the_document_ends_in_exactly_one_newline(make_meeting):
    rendered = render_meeting(make_meeting())
    assert rendered.endswith("\n")
    assert not rendered.endswith("\n\n")


def test_rendering_twice_is_byte_identical(make_meeting):
    first = render_meeting(make_meeting())
    second = render_meeting(make_meeting())
    assert first.encode() == second.encode()


def test_a_round_trip_recovers_the_original_speakers_and_turns(make_meeting):
    meeting = make_meeting()
    recovered = parse_turns(render_meeting(meeting))
    assert recovered == [(turn.speaker, turn.text) for turn in meeting.turns]


def test_a_marker_inside_turn_text_does_not_confuse_the_round_trip(make_meeting):
    meeting = make_meeting(
        turns=[{"speaker": "Priya", "text": "The log line reads [Marcus]: retry."}]
    )
    assert parse_turns(render_meeting(meeting)) == [
        ("Priya", "The log line reads [Marcus]: retry.")
    ]
