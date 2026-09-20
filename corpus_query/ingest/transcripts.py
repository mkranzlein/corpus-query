"""Reading a rendered transcript and cutting it into windows of whole turns.

This is one format reader among several. It reads the rendered markdown a
meeting was written to, and cuts it along the seams a conversation has.

A chunk is built out of whole turns. A turn is the smallest citable unit: it
is one person saying one thing, and half of it attributed to them is a
misquote. So windows accumulate turns until they are about the size we want
and stop there, rather than cutting at a word count.

Windows overlap by one turn. A question and its answer are two turns, and a
window that ends between them leaves the exchange in neither half. Repeating
the boundary turn in the next window costs one turn of storage and means any
adjacent pair is whole somewhere.

Chunk text is the source file's own lines, joined back together with the
newlines that separated them. It is therefore byte-identical to the span of
the document it came from, which is what lets a citation be checked against
the file a reader opens instead of against a re-rendering of it.

A meeting has no author. Who was there is recorded as attendees instead, so
the document row's ``author`` stays null and a question about who was
involved in something is answered from those rows.

Nothing here is random or time-dependent, so reading the same document twice
gives the same chunks.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from corpus_query.ingest.chunk import TARGET_WORDS, Chunk, count_words
from corpus_query.ingest.reader import IngestError, ReadDocument, span_location
from corpus_query.store.kinds import TRANSCRIPT, TURN_WINDOW
from corpus_query.transcripts.parse import (
    ParsedTranscript,
    ParsedTurn,
    TranscriptError,
    parse_file,
)

#: The rendered markdown, not the JSON beside it: chunk text has to be
#: byte-identical to the document a reader opens.
TRANSCRIPT_SUFFIX = ".md"

#: What a turn window's citation label calls the units it spans.
TURN_UNIT = "turn"


def read_transcript(path: Path, target_words: int = TARGET_WORDS) -> ReadDocument:
    """Read one rendered transcript into a document ready to be written.

    Args:
        path: The transcript to read.
        target_words: Words a window aims for.

    Returns:
        The document, with its attendees and its turn windows.

    Raises:
        IngestError: If the file cannot be read, or is not a transcript.
            The message is the parser's, which names the file and what it
            expected to find in it.
    """
    try:
        transcript = parse_file(path)
    except TranscriptError as exc:
        raise IngestError(str(exc)) from exc
    return as_document(transcript, target_words=target_words)


def as_document(
    transcript: ParsedTranscript, target_words: int = TARGET_WORDS
) -> ReadDocument:
    """Chunk an already parsed transcript into a document to be written.

    Args:
        transcript: The parsed transcript.
        target_words: Words a window aims for.

    Returns:
        The document, with its attendees and its turn windows. Its author is
        null: a meeting has participants instead.
    """
    return ReadDocument(
        source_kind=TRANSCRIPT,
        title=transcript.subject,
        document_date=transcript.date,
        author=None,
        attendees=transcript.attendees,
        chunks=tuple(chunk_turns(transcript.turns, target_words=target_words)),
        units=len(transcript.turns),
        unit_name="turns",
    )


def chunk_turns(
    turns: Sequence[ParsedTurn], target_words: int = TARGET_WORDS
) -> list[Chunk]:
    """Cut a transcript's turns into overlapping windows.

    Args:
        turns: The document's turns, in order.
        target_words: Words a window aims for.

    Returns:
        The windows, in document order. Empty if there are no turns.
    """
    counts = [count_words(turn.line) for turn in turns]
    windows = [
        _with_overlap(group, counts, target_words)
        for group in _group(counts, target_words)
    ]
    return [
        _build_chunk(ordinal, turns, start, end)
        for ordinal, (start, end) in enumerate(windows)
    ]


def _group(counts: list[int], target_words: int) -> list[tuple[int, int]]:
    """Partition turn indices into groups that each pass the word target.

    Groups are the backbone of the windows: they cover every turn exactly
    once, and the overlap is added afterwards. A turn that is longer than the
    target on its own always starts a group, which is what keeps it from
    being buried in the middle of one.

    Args:
        counts: Word count per turn.
        target_words: Words a group aims for.

    Returns:
        One inclusive ``(start, end)`` pair per group, in order.
    """
    groups: list[tuple[int, int]] = []
    start = 0
    words = 0
    for index, count in enumerate(counts):
        oversized = count >= target_words
        if index > start and (words >= target_words or oversized):
            groups.append((start, index - 1))
            start = index
            words = 0
        words += count
    if counts:
        groups.append((start, len(counts) - 1))
    return groups


def _with_overlap(
    group: tuple[int, int], counts: list[int], target_words: int
) -> tuple[int, int]:
    """Extend a group left by one turn, so neighboring windows overlap.

    A group whose single turn is already over the target is left alone. Such
    a turn stands as its own chunk rather than being padded or, worse, split.
    The cost is that the boundary between it and the turn before it is not
    carried whole by any window — but a turn that long is self-contained
    enough that a point running into it is mostly inside it anyway.

    Args:
        group: The group's inclusive ``(start, end)`` turn indices.
        counts: Word count per turn.
        target_words: Words a window aims for.

    Returns:
        The window's inclusive ``(start, end)`` turn indices.
    """
    start, end = group
    if start == 0 or (start == end and counts[start] >= target_words):
        return group
    return (start - 1, end)


def _build_chunk(
    ordinal: int, turns: Sequence[ParsedTurn], start: int, end: int
) -> Chunk:
    """Assemble one chunk from an inclusive span of turns.

    Args:
        ordinal: The chunk's position in the document.
        turns: The document's turns.
        start: Index of the first turn in the window.
        end: Index of the last turn in the window, inclusive.

    Returns:
        The chunk.
    """
    text = "\n".join(turn.line for turn in turns[start : end + 1])
    return Chunk(
        ordinal=ordinal,
        text=text,
        word_count=count_words(text),
        kind=TURN_WINDOW,
        location=span_location(TURN_UNIT, start, end),
        span_start=start,
        span_end=end,
    )
