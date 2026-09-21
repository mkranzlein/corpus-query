"""Reading documents and writing them into the document store.

The pipeline is format-agnostic. It dispatches on a file's extension to a
reader, which returns the document's header fields, its people, and its
chunks; everything after that — clearing whatever was there, inserting the
rows, keeping the full-text index in step — is the same whatever the file
was. A transcript is one of the formats it dispatches to rather than the
shape it assumes.

One document is one transaction. A file is read and chunked in full before
anything is written, and the write either lands whole or not at all. A
half-ingested document is the worst outcome available: it looks like a
document, it answers queries, and it is missing the part that mattered.

Ingesting a document that is already in the store replaces it. The slug is
the document's identity, so re-ingesting a document after it has been edited
brings the store up to date instead of adding a second copy of it. Chunk rows
are deleted explicitly rather than left to the foreign key cascade, so that
the triggers keeping ``chunks_fts`` in step are guaranteed to fire.

Nothing here calls a model. Ingestion is deterministic: the same files give
the same rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from corpus_query.ingest.chunk import TARGET_WORDS, Chunk
from corpus_query.ingest.decks import DECK_SUFFIX, read_deck
from corpus_query.ingest.reader import IngestError, ReadDocument, Reader
from corpus_query.ingest.transcripts import TRANSCRIPT_SUFFIX, read_transcript
from corpus_query.ingest.word import DOCX_SUFFIX, read_word_document
from corpus_query.ingest.workbooks import XLSX_SUFFIX, read_workbook

#: Where the corpus lives, relative to the repository root: the transcripts
#: the generator writes, and the office documents committed beside them. A
#: run with no paths named reads all of it, because a corpus is every
#: document in it rather than whichever directory came first.
DEFAULT_DOCUMENT_DIRS = (Path("data/transcripts"), Path("data/office"))

#: What each file extension is read by. A format is added by writing a
#: reader and naming it here; nothing below this table knows how many
#: formats there are.
READERS: dict[str, Reader] = {
    TRANSCRIPT_SUFFIX: read_transcript,
    DOCX_SUFFIX: read_word_document,
    DECK_SUFFIX: read_deck,
    XLSX_SUFFIX: read_workbook,
}


@dataclass(frozen=True)
class Ingested:
    """What ingesting one document did."""

    slug: str
    document_id: int
    source_kind: str
    units: int
    """How many turns, sections, slides, or rows the document held."""

    unit_name: str
    """What those units are called, for a line of output about the run."""

    chunks: int
    replaced: bool
    """Whether a document with this slug was already in the store."""


def document_paths(
    directories: Path | str | Iterable[Path | str] = DEFAULT_DOCUMENT_DIRS,
) -> list[Path]:
    """List the documents in some directories that a reader can read.

    A file whose extension no reader claims is left out rather than reported.
    A corpus directory holds more than its documents — the JSON a transcript
    was rendered from, a spreadsheet whose reader has not been written yet —
    and none of that is a failed ingest.

    Args:
        directories: Where the documents live. One directory or several; a
            lone path is taken as itself rather than iterated, since
            iterating a ``Path`` gives its parts and would silently look in
            the wrong places. A directory that does not exist contributes
            nothing rather than failing the run.

    Returns:
        Every readable file, in name order within each directory, the
        directories in the order given.
    """
    if isinstance(directories, (str, Path)):
        directories = [directories]
    found: list[Path] = []
    for directory in directories:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        found.extend(
            sorted(
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.lower() in READERS
            )
        )
    return found


def reader_for(path: Path | str) -> Reader:
    """Return the reader for a file, chosen by its extension.

    Args:
        path: The file to read.

    Returns:
        The reader registered for its extension.

    Raises:
        IngestError: If no reader claims that extension. Naming a file the
            pipeline cannot read is worth saying so about, which is why this
            is an error here and a skip in :func:`document_paths`.
    """
    path = Path(path)
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        known = ", ".join(sorted(READERS))
        raise IngestError(
            f"There is no reader for {path}. Readable extensions are {known}."
        )
    return reader


def ingest_file(
    connection: sqlite3.Connection,
    path: Path | str,
    target_words: int = TARGET_WORDS,
) -> Ingested:
    """Read, chunk, and store one document.

    Args:
        connection: An open document store.
        path: The document to ingest.
        target_words: Words a chunk aims for, for a format that chunks by
            size.

    Returns:
        What the ingest did.

    Raises:
        IngestError: If no reader claims the file, or the reader cannot read
            it. Nothing is written in that case.
    """
    path = Path(path)
    document = reader_for(path)(path, target_words)
    return write_document(connection, path.stem, path, document)


def ingest_paths(
    connection: sqlite3.Connection,
    paths: Iterable[Path | str],
    target_words: int = TARGET_WORDS,
) -> tuple[list[Ingested], list[IngestError]]:
    """Ingest several documents, one transaction each.

    A file that fails is reported rather than raised, so one unreadable
    document does not strand the rest of a corpus. What it leaves behind is
    nothing: its own transaction rolled back, and every other file's stands.

    Args:
        connection: An open document store.
        paths: The documents to ingest.
        target_words: Words a chunk aims for.

    Returns:
        What was ingested, and one error per file that could not be.
    """
    done: list[Ingested] = []
    failures: list[IngestError] = []
    for path in paths:
        try:
            done.append(ingest_file(connection, path, target_words=target_words))
        except IngestError as exc:
            failures.append(exc)
    return done, failures


def write_document(
    connection: sqlite3.Connection,
    slug: str,
    source_path: Path | str,
    document: ReadDocument,
) -> Ingested:
    """Write one document that a reader has already parsed and chunked.

    Args:
        connection: An open document store.
        slug: The document's identity, normally the file's name without its
            suffix.
        source_path: Where the document was read from, recorded for
            provenance.
        document: The parsed and chunked document.

    Returns:
        What the write did.

    Raises:
        sqlite3.Error: If anything about the write fails. The transaction is
            rolled back first, so the store is left as it was.
    """
    with connection:
        replaced = _delete_document(connection, slug)
        document_id = _insert_document(connection, slug, source_path, document)
        _insert_attendees(connection, document_id, document.attendees)
        _insert_chunks(connection, document_id, document.chunks)
    return Ingested(
        slug=slug,
        document_id=document_id,
        source_kind=document.source_kind,
        units=document.units,
        unit_name=document.unit_name,
        chunks=len(document.chunks),
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
    document: ReadDocument,
) -> int:
    """Insert the document row.

    Args:
        connection: An open document store.
        slug: The document's identity.
        source_path: Where the document was read from.
        document: The parsed document.

    Returns:
        The new document's id.
    """
    cursor = connection.execute(
        """
        INSERT INTO documents
            (slug, source_path, source_kind, title, document_date, author)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            str(source_path),
            document.source_kind,
            document.title,
            document.document_date,
            document.author,
        ),
    )
    return cursor.lastrowid


def _insert_attendees(
    connection: sqlite3.Connection, document_id: int, attendees: Sequence[str]
) -> None:
    """Insert one row per attendee.

    Attendees come from a meeting's header, not from who speaks. Someone who
    sat through a meeting without saying a word was still in it, and a
    question about what a person was involved in has to find that meeting. A
    document with one author has none of these rows and names its author on
    the document row instead.

    Args:
        connection: An open document store.
        document_id: The document these attendees belong to.
        attendees: Everyone the header lists, in order. Empty for a document
            that is not a meeting.
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
            (document_id, ordinal, text, word_count, location,
             span_start, span_end, kind)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                document_id,
                chunk.ordinal,
                chunk.text,
                chunk.word_count,
                chunk.location,
                chunk.span_start,
                chunk.span_end,
                chunk.kind,
            )
            for chunk in chunks
        ],
    )
