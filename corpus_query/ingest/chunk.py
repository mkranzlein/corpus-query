"""What a chunk is, whatever format it was cut out of.

A chunk is one retrievable span of text plus what a citation needs to point
at it: where it sits in its document, what label a reader is shown, and the
range it covers in whatever unit its format counts in — turns, paragraphs,
slides, rows.

The cutting itself is per format and lives with that format's reader.
:mod:`corpus_query.ingest.transcripts` cuts transcripts into windows of whole
turns; an Office format cuts along its own seams. This module holds only what
they all produce, so a new format brings a chunker rather than a second idea
of what a chunk is.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Words a chunk aims for. A chunker adds whole units — a turn, a paragraph —
#: until the total passes it, so a chunk is usually a little over rather than
#: under. Big enough to carry a point made over a few turns, small enough that
#: a retrieved chunk is mostly about one thing.
TARGET_WORDS = 250


@dataclass(frozen=True)
class Chunk:
    """One retrievable span of a document."""

    ordinal: int
    """Position within the document, starting at 0."""

    text: str
    """The span's text, exactly as it appears in the source document."""

    word_count: int
    """Words in ``text``, speaker markers and table pipes included."""

    kind: str
    """How this span was cut, from :mod:`corpus_query.store.kinds`."""

    location: str
    """What a citation shows a reader: a turn range, a heading path, a slide
    number, a sheet and row range. Each format decides what it says."""

    span_start: int | None
    """First unit the span covers, counting in whatever its kind counts in.
    ``None`` for a chunk written about a document rather than cut out of
    one."""

    span_end: int | None
    """Last unit the span covers, inclusive. ``None`` alongside
    ``span_start``."""


def count_words(text: str) -> int:
    """Count whitespace-separated words.

    Markup counts: a speaker marker, a heading, and a table's pipes are all
    part of the text a chunk carries and part of what an embedding or a
    reader sees. This is deliberately not
    :func:`corpus_query.transcripts.length.transcript_words`, which counts
    spoken words only because it is sizing a generation request rather than a
    retrieval unit.

    Args:
        text: The text to measure.

    Returns:
        The number of words.
    """
    return len(text.split())
