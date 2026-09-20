"""What every format reader hands the ingest pipeline.

A reader takes one file and returns a document: its header fields, its
people, and its chunks. It does not touch the store. Everything past this
point — clearing an earlier copy, inserting the rows, keeping the full-text
index in step — is the same whatever the file was, which is what keeps a new
format to a reader and a chunker rather than a second pipeline.

Readers raise :class:`IngestError` rather than a per-format exception, so the
pipeline can report one unreadable file and carry on with the rest of a
corpus without knowing which formats exist.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from corpus_query.ingest.chunk import Chunk


class IngestError(Exception):
    """A file could not be read as the document it claims to be."""


@dataclass(frozen=True)
class ReadDocument:
    """One document, parsed and chunked, ready to be written."""

    source_kind: str
    """What it was read out of, from :mod:`corpus_query.store.kinds`."""

    title: str
    """The document's own title: a meeting's subject, a deck's title."""

    document_date: str
    """When it is dated, as ``YYYY-MM-DD``. A meeting's date, a document's
    last modification."""

    author: str | None
    """Who wrote it, for a format that has one author. ``None`` for a
    transcript, which has attendees instead."""

    attendees: tuple[str, ...]
    """Who was at the meeting. Empty for anything that is not one."""

    chunks: tuple[Chunk, ...]
    """Its chunks, in document order."""

    units: int
    """How many of whatever the format counts in the document holds: turns,
    sections, slides, rows."""

    unit_name: str
    """What those units are called, plural, for a line of output about the
    ingest. ``"turns"``, ``"slides"``."""


#: Reads one file into a document. ``target_words`` is what its chunker aims
#: for; a format whose chunks are fixed by its own structure — one per slide
#: — takes it and ignores it.
type Reader = Callable[[Path, int], ReadDocument]


def span_location(unit: str, start: int, end: int) -> str:
    """Render a citation label for a span of numbered units.

    Args:
        unit: What the units are called, singular. Pluralized by adding an
            ``s``, which holds for every unit any format here counts in.
        start: First unit in the span.
        end: Last unit in the span, inclusive.

    Returns:
        ``"turns 4-9"``, or ``"turn 4"`` when the span is one unit. The
        numbers are the chunk's own ``span_start`` and ``span_end``, so a
        label can be checked against the row it came from.
    """
    if start == end:
        return f"{unit} {start}"
    return f"{unit}s {start}-{end}"
