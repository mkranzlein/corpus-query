"""Reading transcripts and writing them into the document store.

One document is one transaction. A transcript is parsed and chunked in full
before anything is written, and the write — clearing whatever was there,
inserting the document, its attendees, and its chunks — either lands whole or
not at all. A half-ingested document is the worst outcome available: it looks
like a document, it answers queries, and it is missing the part that mattered.

Ingesting a document that is already in the store replaces it. The slug is the
document's identity, so re-ingesting a transcript after it has been edited
brings the store up to date instead of adding a second copy of it. Chunk rows
are deleted explicitly rather than left to the foreign key cascade, so that the
triggers keeping ``chunks_fts`` in step are guaranteed to fire.

Nothing here calls a model. Ingestion is deterministic: the same files give the
same rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from corpus_query.ingest.chunk import CHUNK_KIND, TARGET_WORDS, Chunk, chunk_turns
from corpus_query.transcripts.parse import (
    ParsedTranscript,
    TranscriptError,
    parse_file,
)

#: Where transcripts are written, relative to the repository root. The same
#: directory the generator writes to.
DEFAULT_TRANSCRIPT_DIR = Path("data/transcripts")

#: The rendered markdown, not the JSON beside it: chunk text has to be
#: byte-identical to the document a reader opens.
TRANSCRIPT_SUFFIX = ".md"


@dataclass(frozen=True)
class Ingested:
    """What ingesting one transcript did."""

    slug: str
    document_id: int
    turns: int
    chunks: int
    replaced: bool
    """Whether a document with this slug was already in the store."""


def transcript_paths(directory: Path | str = DEFAULT_TRANSCRIPT_DIR) -> list[Path]:
    """List the transcripts in a directory.

    Args:
        directory: Where transcripts live.

    Returns:
        Every markdown file in the directory, in name order. Empty when the
        directory does not exist.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"*{TRANSCRIPT_SUFFIX}"))


def ingest_file(
    connection: sqlite3.Connection,
    path: Path | str,
    target_words: int = TARGET_WORDS,
) -> Ingested:
    """Parse, chunk, and store one transcript.

    Args:
        connection: An open document store.
        path: The transcript to ingest.
        target_words: Words a chunk aims for.

    Returns:
        What the ingest did.

    Raises:
        TranscriptError: If the file cannot be read or is not a transcript.
            Nothing is written in that case.
    """
    path = Path(path)
    transcript = parse_file(path)
    chunks = chunk_turns(transcript.turns, target_words=target_words)
    return write_document(connection, path.stem, path, transcript, chunks)


def ingest_paths(
    connection: sqlite3.Connection,
    paths: Iterable[Path | str],
    target_words: int = TARGET_WORDS,
) -> tuple[list[Ingested], list[TranscriptError]]:
    """Ingest several transcripts, one transaction each.

    A file that fails is reported rather than raised, so one unreadable
    transcript does not strand the rest of a corpus. What it leaves behind is
    nothing: its own transaction rolled back, and every other file's stands.

    Args:
        connection: An open document store.
        paths: The transcripts to ingest.
        target_words: Words a chunk aims for.

    Returns:
        What was ingested, and one error per file that could not be.
    """
    done: list[Ingested] = []
    failures: list[TranscriptError] = []
    for path in paths:
        try:
            done.append(ingest_file(connection, path, target_words=target_words))
        except TranscriptError as exc:
            failures.append(exc)
    return done, failures


def write_document(
    connection: sqlite3.Connection,
    slug: str,
    source_path: Path | str,
    transcript: ParsedTranscript,
    chunks: Sequence[Chunk],
) -> Ingested:
    """Write one parsed and chunked transcript, replacing any earlier copy.

    Args:
        connection: An open document store.
        slug: The document's identity, normally the transcript's filename
            without its suffix.
        source_path: Where the transcript was read from, recorded for
            provenance.
        transcript: The parsed transcript.
        chunks: Its chunks, in order.

    Returns:
        What the write did.

    Raises:
        sqlite3.Error: If anything about the write fails. The transaction is
            rolled back first, so the store is left as it was.
    """
    with connection:
        replaced = _delete_document(connection, slug)
        document_id = _insert_document(connection, slug, source_path, transcript)
        _insert_attendees(connection, document_id, transcript.attendees)
        _insert_chunks(connection, document_id, chunks)
    return Ingested(
        slug=slug,
        document_id=document_id,
        turns=len(transcript.turns),
        chunks=len(chunks),
        replaced=replaced,
    )


def _delete_document(connection: sqlite3.Connection, slug: str) -> bool:
    """Remove a document and everything hanging off it.

    Chunks go first and by hand. A foreign key cascade does not reliably fire
    the delete triggers that keep ``chunks_fts`` in step, and an index still
    holding the text of chunks that no longer exist would answer searches with
    rows nothing can resolve.

    Args:
        connection: An open document store.
        slug: The document's identity.

    Returns:
        Whether there was anything to remove.
    """
    row = connection.execute(
        "SELECT id FROM documents WHERE slug = ?", (slug,)
    ).fetchone()
    if row is None:
        return False
    document_id = row["id"]
    connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
    connection.execute("DELETE FROM attendees WHERE document_id = ?", (document_id,))
    connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    return True


def _insert_document(
    connection: sqlite3.Connection,
    slug: str,
    source_path: Path | str,
    transcript: ParsedTranscript,
) -> int:
    """Insert the document row.

    Args:
        connection: An open document store.
        slug: The document's identity.
        source_path: Where the transcript was read from.
        transcript: The parsed transcript.

    Returns:
        The new document's id.
    """
    cursor = connection.execute(
        """
        INSERT INTO documents (slug, source_path, subject, meeting_date)
        VALUES (?, ?, ?, ?)
        """,
        (slug, str(source_path), transcript.subject, transcript.date),
    )
    return cursor.lastrowid


def _insert_attendees(
    connection: sqlite3.Connection, document_id: int, attendees: Sequence[str]
) -> None:
    """Insert one row per attendee.

    Attendees come from the header, not from who speaks. Someone who sat
    through a meeting without saying a word was still in it, and a question
    about what a person was involved in has to find that meeting.

    Args:
        connection: An open document store.
        document_id: The document these attendees belong to.
        attendees: Everyone the header lists, in order.
    """
    connection.executemany(
        "INSERT INTO attendees (document_id, name) VALUES (?, ?)",
        [(document_id, name) for name in attendees],
    )


def _insert_chunks(
    connection: sqlite3.Connection, document_id: int, chunks: Sequence[Chunk]
) -> None:
    """Insert the document's chunks.

    Args:
        connection: An open document store.
        document_id: The document these chunks belong to.
        chunks: The chunks, in order.
    """
    connection.executemany(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, word_count, turn_start, turn_end, kind)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                document_id,
                chunk.ordinal,
                chunk.text,
                chunk.word_count,
                chunk.turn_start,
                chunk.turn_end,
                CHUNK_KIND,
            )
            for chunk in chunks
        ],
    )
