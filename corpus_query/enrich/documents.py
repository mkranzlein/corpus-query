"""Reading a stored document back out, for a model to work on.

Enrichment reads the store rather than the source files. The store is the
system of record, and a source file can be moved, edited, or absent on the
machine doing the enriching; the rows cannot.

That means reassembling the document from its chunks. A transcript's windows
overlap by one turn on purpose — an exchange split between two windows is
whole in neither — so joining them blindly would repeat a turn. Because a
chunk carries the span it covers, and a transcript chunk's text is one line
per turn, the overlap is dropped by counting lines rather than by comparing
text. A format whose chunks do not overlap passes through that arithmetic
unchanged.

The header a prompt sees depends on what the document is. A meeting has a
subject and the people who sat in it; a document written by one person has a
title and an author. Rendering the wrong one would put a model's attention on
a field that is empty or a mechanism the format does not use.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from corpus_query.enrich.errors import EnrichmentError
from corpus_query.store.kinds import SUMMARY, TRANSCRIPT


@dataclass(frozen=True)
class StoredDocument:
    """One document, as the enrichment prompts need to see it."""

    id: int
    slug: str
    source_kind: str
    """What the document was read out of, from
    :mod:`corpus_query.store.kinds`."""

    title: str
    document_date: str
    author: str | None
    """Who wrote it, or ``None`` for a transcript."""

    attendees: tuple[str, ...]
    """Who was at the meeting. Empty for anything that is not one."""

    text: str
    """The document, reassembled from its chunks with any overlap removed."""


def pending_ids(connection: sqlite3.Connection) -> list[int]:
    """Return the documents that have not been enriched yet.

    The summary is what "enriched" is judged by: it is written in the same
    transaction as the topics and the priority fields, so a document that
    has one has all of them.

    Args:
        connection: An open document store.

    Returns:
        Document ids, oldest first.
    """
    return [
        row["id"]
        for row in connection.execute(
            "SELECT id FROM documents WHERE summary IS NULL ORDER BY id"
        )
    ]


def ids_for_slugs(connection: sqlite3.Connection, slugs: Sequence[str]) -> list[int]:
    """Look up specific documents by slug.

    Args:
        connection: An open document store.
        slugs: The documents to enrich, named as they were ingested.

    Returns:
        Their ids, in the order the slugs were given.

    Raises:
        EnrichmentError: If any slug is not in the store. Naming a document
            that does not exist is a typo worth failing on rather than a
            shorter run than asked for.
    """
    ids = []
    for slug in slugs:
        row = connection.execute(
            "SELECT id FROM documents WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            raise EnrichmentError(f"There is no document with the slug {slug!r}.")
        ids.append(row["id"])
    return ids


def read_document(connection: sqlite3.Connection, document_id: int) -> StoredDocument:
    """Read one document and reassemble its text.

    Args:
        connection: An open document store.
        document_id: The document to read.

    Returns:
        The document, with its people and its text.

    Raises:
        EnrichmentError: If there is no such document, or it has no chunks
            to reassemble it from.
    """
    row = connection.execute(
        """
        SELECT id, slug, source_kind, title, document_date, author
        FROM documents
        WHERE id = ?
        """,
        (document_id,),
    ).fetchone()
    if row is None:
        raise EnrichmentError(f"There is no document with the id {document_id}.")
    text = document_text(connection, document_id)
    if not text:
        raise EnrichmentError(
            f"Document {row['slug']!r} has no chunks to enrich. Ingest it again."
        )
    return StoredDocument(
        id=row["id"],
        slug=row["slug"],
        source_kind=row["source_kind"],
        title=row["title"],
        document_date=row["document_date"],
        author=row["author"],
        attendees=_attendees(connection, document_id),
        text=text,
    )


def document_text(connection: sqlite3.Connection, document_id: int) -> str:
    """Reassemble a document's text from its chunks.

    Every chunk cut out of the document goes in, in ordinal order. The
    summary chunk enrichment writes is left out: it is about the document
    rather than part of it, and feeding a summary back in as source material
    is how the next summary comes to summarize the last one.

    Args:
        connection: An open document store.
        document_id: The document to reassemble.

    Returns:
        The document's own text, each line appearing once. Empty when the
        document has no chunks but a summary.
    """
    rows = connection.execute(
        """
        SELECT text, span_start, span_end
        FROM chunks
        WHERE document_id = ? AND kind <> ?
        ORDER BY ordinal
        """,
        (document_id, SUMMARY),
    ).fetchall()

    lines: list[str] = []
    next_unit = 0
    for row in rows:
        chunk_lines = row["text"].split("\n")
        # How many of this chunk's leading lines the previous chunk already
        # carried, for a format whose chunks overlap. Negative never happens
        # for chunks from one ingest, but a gap would only mean units are
        # missing, not repeated, so it is clamped rather than treated as an
        # error.
        start = row["span_start"]
        overlap = (
            0 if start is None else max(0, min(len(chunk_lines), next_unit - start))
        )
        lines.extend(chunk_lines[overlap:])
        if row["span_end"] is not None:
            next_unit = max(next_unit, row["span_end"] + 1)
    return "\n".join(lines)


def describe(document: StoredDocument) -> str:
    """Render a document for a prompt.

    A transcript is rendered the way its markdown reads — a subject, a date,
    and who was there — so a model sees the document the way a reader would.
    Anything else carries one author rather than a list of attendees, and is
    rendered with an author line in place of that one.

    Args:
        document: The document to render.

    Returns:
        Its header fields and its text.
    """
    return "\n".join([*_header(document), "", document.text])


def _header(document: StoredDocument) -> list[str]:
    """Render the header lines for a document, chosen by its kind.

    Args:
        document: The document to render a header for.

    Returns:
        One line per header field, in the order that format writes them.
    """
    if document.source_kind == TRANSCRIPT:
        return [
            f"**Subject:** {document.title}",
            f"**Date:** {document.document_date}",
            f"**Attendees:** {', '.join(document.attendees)}",
        ]
    return [
        f"**Title:** {document.title}",
        f"**Date:** {document.document_date}",
        f"**Author:** {document.author or 'unknown'}",
    ]


def _attendees(connection: sqlite3.Connection, document_id: int) -> tuple[str, ...]:
    """Return who was at a meeting.

    Args:
        connection: An open document store.
        document_id: The document.

    Returns:
        The attendee names, in the order the header listed them.
    """
    return tuple(
        row["name"]
        for row in connection.execute(
            "SELECT name FROM attendees WHERE document_id = ? ORDER BY id",
            (document_id,),
        )
    )
