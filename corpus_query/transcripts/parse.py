"""Reading a rendered transcript back into its parts.

Every meeting is written to disk twice: as JSON, which is the easier thing to
read, and as markdown, which is the thing a person opens. Ingestion reads the
markdown, because a citation is only sound if the text backing it is
byte-identical to the document someone can go and look at. Reading the JSON and
re-rendering it would almost always agree, and the one time it did not would be
the time it mattered.

That is only safe because the rendered format is unambiguous by construction.
A turn is one line, the speaker marker is at the start of it, and ``]`` cannot
appear in a name, so the first ``]: `` on a line always closes the marker.
A turn whose text happens to contain ``[Marcus]:`` therefore still reads back
correctly. :mod:`corpus_query.transcripts.render` is the other half of this
guarantee, and the round-trip test is what keeps the two honest.

Parsing is strict. A file that is not a transcript, or one whose transcript
section holds a line that is not a turn, raises rather than yielding a document
with a hole in it. Half a transcript in the store is worse than none: it
retrieves, it cites, and it is wrong.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from pathlib import Path

#: A rendered turn: the marker at the start of the line, then what was said.
SPEAKER_MARKER = re.compile(r"^\[([^\]]+)\]: (.+)$")

#: Section headings, in the order the renderer writes them.
SUBJECT_PREFIX = "# "
TRANSCRIPT_HEADING = "## Transcript"
DECISIONS_HEADING = "## Decisions"

#: Header field prefixes.
DATE_PREFIX = "- **Date:** "
ATTENDEES_PREFIX = "- **Attendees:** "

#: What separates attendees in the header line.
ATTENDEE_SEPARATOR = ", "


class TranscriptError(Exception):
    """A file is not a transcript, or is not shaped like one."""


@dataclass(frozen=True)
class ParsedTurn:
    """One turn, as it was read out of a rendered transcript."""

    speaker: str
    text: str
    line: str
    """The source line this turn was read from, marker included.

    Kept rather than re-rendered so that chunk text can be assembled from the
    file's own bytes instead of from something that ought to match them.
    """


@dataclass(frozen=True)
class ParsedTranscript:
    """A rendered transcript, read back into its header fields and its turns.

    Decisions and action items are not read. They are rendered from the same
    meeting the turns came from, and nothing downstream of ingestion asks for
    them yet; when something does, this is where they go.
    """

    subject: str
    date: str
    attendees: tuple[str, ...]
    turns: tuple[ParsedTurn, ...]
    source: str
    """Where the markdown came from, for error messages and provenance."""


def parse_file(path: Path | str) -> ParsedTranscript:
    """Read and parse one rendered transcript.

    Args:
        path: Path to the markdown file.

    Returns:
        The parsed transcript.

    Raises:
        TranscriptError: If the file cannot be read, or is not a transcript.
    """
    path = Path(path)
    try:
        markdown = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TranscriptError(
            f"Could not read the transcript at {path}: {exc}"
        ) from exc
    return parse_transcript(markdown, source=str(path))


def parse_transcript(markdown: str, source: str = "<transcript>") -> ParsedTranscript:
    """Parse a rendered transcript.

    Args:
        markdown: The rendered document.
        source: Where the markdown came from. Named in error messages, and
            carried on the result.

    Returns:
        The parsed transcript.

    Raises:
        TranscriptError: If any part of the document is missing or malformed.
            The message names the source and what was expected.
    """
    lines = markdown.splitlines()
    subject = _parse_subject(lines, source)
    date = _parse_date(lines, source)
    attendees = _parse_attendees(lines, source)
    turns = _parse_turns(lines, source)
    return ParsedTranscript(
        subject=subject,
        date=date,
        attendees=attendees,
        turns=turns,
        source=source,
    )


def _parse_subject(lines: list[str], source: str) -> str:
    """Return the meeting subject from the document's title line.

    Args:
        lines: The document, split into lines.
        source: Where the markdown came from, for the error message.

    Returns:
        The subject.

    Raises:
        TranscriptError: If the document does not open with a title.
    """
    for line in lines:
        if not line.strip():
            continue
        if not line.startswith(SUBJECT_PREFIX):
            break
        subject = line.removeprefix(SUBJECT_PREFIX).strip()
        if subject:
            return subject
        break
    raise TranscriptError(
        f"{source} does not start with a meeting subject written as "
        f"'{SUBJECT_PREFIX}Subject'."
    )


def _parse_date(lines: list[str], source: str) -> str:
    """Return the meeting date from the header.

    Args:
        lines: The document, split into lines.
        source: Where the markdown came from, for the error message.

    Returns:
        The date, as ``YYYY-MM-DD``.

    Raises:
        TranscriptError: If the date line is missing or is not a calendar date.
    """
    value = _find_field(lines, DATE_PREFIX, source)
    try:
        return datetime.date.fromisoformat(value).isoformat()
    except ValueError:
        raise TranscriptError(
            f"{source} has a date of {value!r}, where a calendar date written "
            f"as YYYY-MM-DD was expected."
        ) from None


def _parse_attendees(lines: list[str], source: str) -> tuple[str, ...]:
    """Return everyone the header says was present.

    Who attended is taken from the header rather than from who speaks. An
    attendee who sat through a meeting without saying anything was still
    there, and a search for the meetings someone sat in has to find it.

    Args:
        lines: The document, split into lines.
        source: Where the markdown came from, for the error message.

    Returns:
        The attendees, in the order the header lists them.

    Raises:
        TranscriptError: If the attendees line is missing or lists nobody.
    """
    value = _find_field(lines, ATTENDEES_PREFIX, source)
    attendees = tuple(
        name.strip() for name in value.split(ATTENDEE_SEPARATOR) if name.strip()
    )
    if not attendees:
        raise TranscriptError(f"{source} lists no attendees in its header.")
    return attendees


def _find_field(lines: list[str], prefix: str, source: str) -> str:
    """Return the value of a header field.

    Args:
        lines: The document, split into lines.
        prefix: What the field's line starts with.
        source: Where the markdown came from, for the error message.

    Returns:
        Whatever follows the prefix, trimmed.

    Raises:
        TranscriptError: If no line carries the prefix, or the value is empty.
    """
    for line in lines:
        if line.startswith(prefix):
            value = line.removeprefix(prefix).strip()
            if value:
                return value
            break
        if line == TRANSCRIPT_HEADING:
            break
    raise TranscriptError(
        f"{source} has no header line beginning '{prefix.strip()}', which every "
        f"transcript carries."
    )


def _parse_turns(lines: list[str], source: str) -> tuple[ParsedTurn, ...]:
    """Return the turns between the transcript heading and the one after it.

    Args:
        lines: The document, split into lines.
        source: Where the markdown came from, for the error message.

    Returns:
        One entry per turn, in transcript order.

    Raises:
        TranscriptError: If either heading is missing, if a line in the
            transcript section is not a turn, or if there are no turns at all.
    """
    start = _heading_index(lines, TRANSCRIPT_HEADING, source)
    end = _heading_index(lines, DECISIONS_HEADING, source)
    if end < start:
        raise TranscriptError(
            f"{source} has its {DECISIONS_HEADING!r} heading before its "
            f"{TRANSCRIPT_HEADING!r} heading."
        )

    turns = []
    for offset, line in enumerate(lines[start + 1 : end], start=start + 2):
        if not line.strip():
            continue
        match = SPEAKER_MARKER.match(line)
        if match is None:
            raise TranscriptError(
                f"{source} line {offset} is in the transcript but is not a "
                f"turn; a turn is written as '[Name]: what they said'. Found: "
                f"{line!r}"
            )
        turns.append(ParsedTurn(speaker=match.group(1), text=match.group(2), line=line))
    if not turns:
        raise TranscriptError(f"{source} has a transcript section with no turns.")
    return tuple(turns)


def _heading_index(lines: list[str], heading: str, source: str) -> int:
    """Return the line number of a heading.

    Args:
        lines: The document, split into lines.
        heading: The heading to find, exactly as the renderer writes it.
        source: Where the markdown came from, for the error message.

    Returns:
        The index of the heading within ``lines``.

    Raises:
        TranscriptError: If the heading does not appear.
    """
    try:
        return lines.index(heading)
    except ValueError:
        raise TranscriptError(
            f"{source} has no {heading!r} heading, which every transcript carries."
        ) from None
