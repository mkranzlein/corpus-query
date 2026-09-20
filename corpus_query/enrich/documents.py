"""Reading a stored document back out, for a model to work on.

Enrichment reads the store rather than the transcript files. The store is
the system of record, and a source file can be moved, edited, or absent on
the machine doing the enriching; the rows cannot.

That means reassembling the transcript from its chunks. Chunks overlap by one
turn on purpose — an exchange split between two windows is whole in neither —
so joining them blindly would repeat a turn. Because a chunk carries the turn
range it spans, and a chunk's text is one line per turn, the overlap is
dropped by counting lines rather than by comparing text.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from corpus_query.enrich.errors import EnrichmentError

#: The chunk kind ingestion writes, and the only kind reassembled into the
#: transcript. A summary chunk is about the document rather than part of it.
TURN_WINDOW = "turn_window"

#: What ``chunks.kind`` holds for the chunk enrichment writes.
SUMMARY = "summary"


@dataclass(frozen=True)
class StoredDocument:
    """One document, as the enrichment prompts need to see it."""

    id: int
    slug: str
    subject: str
    meeting_date: str
    attendees: tuple[str, ...]
    text: str
    """The transcript, reassembled from its chunks with the overlap removed."""


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
    """Read one document and reassemble its transcript.

    Args:
        connection: An open document store.
        document_id: The document to read.

    Returns:
        The document, with its attendees and its transcript text.

    Raises:
        EnrichmentError: If there is no such document, or it has no chunks
            to reassemble a transcript from.
    """
    row = connection.execute(
        "SELECT id, slug, subject, meeting_date FROM documents WHERE id = ?",
        (document_id,),
    ).fetchone()
    if row is None:
        raise EnrichmentError(f"There is no document with the id {document_id}.")
    text = transcript_text(connection, document_id)
    if not text:
        raise EnrichmentError(
            f"Document {row['slug']!r} has no chunks to enrich. Ingest it again."
        )
    return StoredDocument(
        id=row["id"],
        slug=row["slug"],
        subject=row["subject"],
        meeting_date=row["meeting_date"],
        attendees=_attendees(connection, document_id),
        text=text,
    )


def transcript_text(connection: sqlite3.Connection, document_id: int) -> str:
    """Reassemble a document's transcript from its chunks.

    Args:
        connection: An open document store.
        document_id: The document to reassemble.

    Returns:
        The transcript's turns, one per line, in order and each appearing
        once. Empty when the document has no turn windows.
    """
    rows = connection.execute(
        """
        SELECT text, turn_start, turn_end
        FROM chunks
        WHERE document_id = ? AND kind = ?
        ORDER BY ordinal
        """,
        (document_id, TURN_WINDOW),
    ).fetchall()

    lines: list[str] = []
    next_turn = 0
    for row in rows:
        chunk_lines = row["text"].split("\n")
        # How many of this chunk's leading turns the previous one already
        # carried. Negative never happens for chunks from one ingest, but a
        # gap would only mean turns are missing, not repeated, so it is
        # clamped rather than treated as an error.
        overlap = max(0, min(len(chunk_lines), next_turn - row["turn_start"]))
        lines.extend(chunk_lines[overlap:])
        next_turn = max(next_turn, row["turn_end"] + 1)
    return "\n".join(lines)


def describe(document: StoredDocument) -> str:
    """Render a document for a prompt.

    Args:
        document: The document to render.

    Returns:
        Its header fields and its transcript, in the shape the rendered
        markdown uses, so a model sees the document the way a reader would.
    """
    return "\n".join(
        [
            f"**Subject:** {document.subject}",
            f"**Date:** {document.meeting_date}",
            f"**Attendees:** {', '.join(document.attendees)}",
            "",
            document.text,
        ]
    )


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
