"""Cutting a transcript into retrievable windows.

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

Nothing here is random or time-dependent, so chunking the same document twice
gives the same chunks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from corpus_query.transcripts.parse import ParsedTurn

#: Words a window aims for. Turns are added until the total passes it, so a
#: window is usually a little over rather than under. Big enough to carry a
#: point made over a few turns, small enough that a retrieved chunk is mostly
#: about one thing.
TARGET_WORDS = 250

#: What ``chunks.kind`` holds for everything this module produces. Enrichment
#: writes ``summary`` chunks later; these are spans of a transcript.
CHUNK_KIND = "turn_window"


@dataclass(frozen=True)
class Chunk:
    """One window of consecutive turns."""

    ordinal: int
    """Position within the document, starting at 0."""

    text: str
    """The window's lines, exactly as they appear in the source file."""

    word_count: int
    """Words in ``text``, speaker markers included."""

    turn_start: int
    """Index of the first turn in the window, counting from 0."""

    turn_end: int
    """Index of the last turn in the window, inclusive."""


def count_words(text: str) -> int:
    """Count whitespace-separated words.

    Speaker markers count, because they are part of the text a chunk carries
    and part of what an embedding or a reader sees. This is deliberately not
    :func:`corpus_query.transcripts.length.transcript_words`, which counts
    spoken words only because it is sizing a generation request rather than a
    retrieval unit.

    Args:
        text: The text to measure.

    Returns:
        The number of words.
    """
    return len(text.split())


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
        turn_start=start,
        turn_end=end,
    )
