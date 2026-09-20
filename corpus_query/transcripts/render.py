"""Turning a validated meeting into markdown.

Rendering is deliberately ours rather than a model's. A model is asked for
facts in a fixed shape; the document those facts appear in is produced here,
by code, so the structure is guaranteed rather than hoped for, and so the
markdown can be rebuilt from the stored objects without paying for generation
again.

The format's one hard rule is that a turn occupies exactly one line. A turn is
written as ``[Name]: what they said``, with the marker at the start of the
line. The schema has already collapsed the text onto one line and forbidden
``]`` in a speaker's name, so the first ``]: `` on the line always closes the
marker. A turn whose text happens to contain something like ``[Marcus]:`` is
therefore still read back correctly.
"""

from __future__ import annotations

from corpus_query.transcripts.schema import Meeting

#: Stand-in for a section that has nothing in it.
EMPTY_SECTION = "_None._"

#: Separator between a rendered speaker marker and what they said.
SPEAKER_SEPARATOR = "]: "


def render_turn(speaker: str, text: str) -> str:
    """Render one turn as a single line.

    Args:
        speaker: The speaker's first name.
        text: What they said, already on one line.

    Returns:
        The line, marker first.
    """
    return f"[{speaker}{SPEAKER_SEPARATOR}{text}"


def render_meeting(meeting: Meeting) -> str:
    """Render one meeting as markdown.

    The output has four sections in a fixed order: the header metadata, the
    transcript, the decisions, and the action items. Nothing about it varies
    between calls, so rendering the same meeting twice gives byte-identical
    text.

    Args:
        meeting: A validated meeting.

    Returns:
        The markdown document, ending in exactly one newline.
    """
    lines = [
        f"# {meeting.subject}",
        "",
        f"- **Date:** {meeting.date}",
        f"- **Attendees:** {', '.join(meeting.attendees)}",
        "",
        "## Transcript",
        "",
    ]
    lines.extend(render_turn(turn.speaker, turn.text) for turn in meeting.turns)
    lines.extend(["", "## Decisions", ""])
    lines.extend([f"- {decision}" for decision in meeting.decisions] or [EMPTY_SECTION])
    lines.extend(["", "## Action items", ""])
    lines.extend(
        [f"- **{item.assignee}:** {item.task}" for item in meeting.action_items]
        or [EMPTY_SECTION]
    )
    return "\n".join(lines) + "\n"
