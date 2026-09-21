"""Recording what the system got wrong, and reading it back.

Three kinds of record, deliberately not one. A **gap** is system-detected: the
record did not settle a question, so the agent abstained, and the row is
written without anybody remembering to file it. A **correction** is
user-supplied and says what was wrong and what is right. **Feedback** is a
verdict — up or down — with an optional note. A bare thumbs down is feedback
rather than a correction: it asserts that an answer was bad and carries
nothing a reader can act on, and a queue of things to act on that is full of
them wastes the reader's time.

All three hang off an **answer row**, written once per question asked. That
row is what gives a correction typed a week later something stable to point
at, and it is the one record per query in the system: anything later that
wants per-query numbers adds columns here rather than a second table
recording the same event.

Everything goes in the usage database, which is the local, uncommitted file
that already holds the agent's graph checkpoints. See
:mod:`corpus_query.store.usage` for why that is a different file from the
corpus. Asking a question, correcting an answer, and reading either back all
leave the committed corpus untouched.

Reviewing
=========

Each gap, correction, and piece of feedback carries ``reviewed_at``: null
while it is new, and the time someone reading the queue marked it seen once
they have. It is the one thing about a record that changes after it is
written, and it changes nothing else about it — the question, the answer,
and what the user said stay exactly as they were recorded. Clearing it puts
an item back among the new ones, so a mistaken click is not permanent.

Why the schema version is a row rather than the ``user_version`` pragma
=======================================================================

The document store records its schema version in SQLite's ``user_version``
pragma, which is what that pragma is for, and this module does not.

The difference is ownership. The document store is a file this project
creates and is the only writer of, so one version number describes the whole
of it. The usage database is shared: LangGraph's checkpointer creates its own
tables in it, on its own schedule, and does not set ``user_version``. Writing
corpus-query's version into a property of the whole file would be claiming to
speak for tables this project does not own — and it would break in both
directions, since a future checkpointer release that started versioning
itself would either be refused by this code or silently overwrite it.

So the version lives in ``capture_meta``, a table these tables own, and the
file-level pragma is left alone. Each writer in a shared file versions its
own tables; nothing versions the file.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from corpus_query.store.usage import usage_database

#: The version of these tables that this code reads and writes. Recorded in
#: ``capture_meta`` rather than in the file's ``user_version`` pragma, for
#: the reasons in the module docstring.
SCHEMA_VERSION = 2

#: The key the version is stored under in ``capture_meta``.
SCHEMA_VERSION_KEY = "schema_version"

#: The verdicts feedback may carry. Enforced by the schema as well, so a
#: third value cannot arrive through a caller that skipped validation.
VERDICTS = ("up", "down")

#: How many records a read returns when it is not told otherwise.
DEFAULT_RECORDS = 50

#: The most one read may ask for. These reads are for a person catching up on
#: what the system got wrong, not for exporting the table.
MAX_RECORDS = 200

_SCHEMA_PATH = Path(__file__).parent / "capture.sql"

#: The three kinds of record, by the names of their tables. Each can be read
#: by id and marked reviewed. The names are the tables' own, which is what
#: makes them safe to interpolate where a parameter cannot go — and why a
#: kind is checked against this list before it gets that far.
KINDS = ("gaps", "corrections", "feedback")

#: What takes a file from each older version to the next one, keyed by the
#: version it starts from. A version-1 file predates reviewing, so its rows
#: gain a null ``reviewed_at``, which reads, correctly, as not yet seen.
_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: tuple(f"ALTER TABLE {table} ADD COLUMN reviewed_at TEXT" for table in KINDS),
}


class CaptureSchemaVersionError(Exception):
    """The captured records are at a version this code does not know."""


class UnknownAnswerError(LookupError):
    """A record was written against an answer id that is not in the store."""


class UnknownRecordError(LookupError):
    """No gap, correction, or piece of feedback has the id that was named."""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the usage database and make sure these tables are in it.

    Args:
        path: Where the usage database lives, or None for the project's
            default. The file and the directory holding it are created if
            they are not there yet.

    Returns:
        An open connection with foreign key enforcement on and rows
        returned as :class:`sqlite3.Row`.

    Raises:
        CaptureSchemaVersionError: If the file already holds these tables at
            a version this code does not know how to work with.
    """
    connection = sqlite3.connect(usage_database(path))
    connection.row_factory = sqlite3.Row
    # Off by default in SQLite, and scoped to the connection rather than the
    # file, so it has to be set every time one is opened. Without it a
    # correction against an id that does not exist would be stored as an
    # orphan instead of refused.
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _initialize(connection)
    except BaseException:
        connection.close()
        raise
    return connection


def _initialize(connection: sqlite3.Connection) -> None:
    """Create these tables, or check the version of the ones already there.

    Only this project's tables are looked at. The file may hold anybody
    else's — the graph checkpoints do — and whether they are present says
    nothing about whether these are.

    Args:
        connection: An open connection, with foreign keys already enabled.

    Raises:
        CaptureSchemaVersionError: If the recorded version is not
            :data:`SCHEMA_VERSION`.
    """
    if not _has_tables(connection):
        connection.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO capture_meta (key, value) VALUES (?, ?)",
            (SCHEMA_VERSION_KEY, str(SCHEMA_VERSION)),
        )
        connection.commit()
        return
    version = _recorded_version(connection)
    if version in _MIGRATIONS:
        _migrate(connection, version)
        return
    if version != SCHEMA_VERSION:
        raise CaptureSchemaVersionError(
            f"the captured records in this usage database are at version "
            f"{version}, but this code only knows how to work with version "
            f"{SCHEMA_VERSION}. The usage database is local and not "
            f"committed, so deleting it is a supported way out — it costs "
            f"the conversations and records it held and nothing else."
        )


def _migrate(connection: sqlite3.Connection, version: int) -> None:
    """Bring these tables from an older version up to the current one.

    Every step runs in one transaction with the version bump, so a file is
    either wholly at the new version or untouched at the old one. The rows
    already there are kept: the usage database is local and not committed,
    and asking someone to delete theirs to pick up a new column would cost
    them every record it held.

    The transaction is opened with an explicit ``BEGIN``. In its default
    mode, Python's :mod:`sqlite3` opens a transaction on its own only before
    an INSERT, UPDATE, DELETE, or REPLACE, never before DDL, so under a bare
    ``with connection:`` each ``ALTER TABLE`` would commit the moment it
    ran. A failure partway through would then leave some columns added and
    the old version recorded, and every later open would retry the first
    ALTER and fail on a column that already exists. SQLite's DDL is
    transactional, so inside an explicit transaction the ALTERs roll back
    with everything else.

    Args:
        connection: An open connection whose tables are at ``version``,
            with no transaction in progress.
        version: The version recorded in the file, a key of
            :data:`_MIGRATIONS`.
    """
    connection.execute("BEGIN")
    try:
        while version != SCHEMA_VERSION:
            for statement in _MIGRATIONS[version]:
                connection.execute(statement)
            version += 1
        connection.execute(
            "UPDATE capture_meta SET value = ? WHERE key = ?",
            (str(SCHEMA_VERSION), SCHEMA_VERSION_KEY),
        )
    except BaseException:
        connection.rollback()
        raise
    connection.commit()


def _has_tables(connection: sqlite3.Connection) -> bool:
    """Return whether this project's tables are already in the file.

    Args:
        connection: An open connection.

    Returns:
        Whether ``capture_meta`` exists.
    """
    return (
        connection.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'capture_meta'"
        ).fetchone()[0]
        > 0
    )


def _recorded_version(connection: sqlite3.Connection) -> int | None:
    """Read the version recorded alongside these tables.

    Args:
        connection: An open connection whose file holds ``capture_meta``.

    Returns:
        The version, or None if the table is there without one — which is a
        file written by something other than this module, and is reported
        the same way a mismatch is.
    """
    row = connection.execute(
        "SELECT value FROM capture_meta WHERE key = ?", (SCHEMA_VERSION_KEY,)
    ).fetchone()
    if row is None:
        return None
    try:
        return int(row["value"])
    except ValueError:
        return None


def record_answer(
    connection: sqlite3.Connection,
    query: str,
    answer: str,
    citations: list[dict[str, Any]],
    thread_id: str,
    abstained: bool,
) -> str:
    """Write the row for one answered question.

    Args:
        connection: An open capture connection.
        query: The question as it was asked.
        answer: The prose the agent wrote. An abstention is a normal value.
        citations: The passages the answer rests on, best first.
        thread_id: The conversation the answer belongs to.
        abstained: Whether the record failed to settle the question.

    Returns:
        The new row's id, which is what a later gap, correction, or piece of
        feedback points at.
    """
    answer_id = uuid.uuid4().hex
    with connection:
        connection.execute(
            "INSERT INTO answers "
            "(id, thread_id, query, answer, citations, abstained) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                answer_id,
                thread_id,
                query,
                answer,
                json.dumps(citations),
                int(abstained),
            ),
        )
    return answer_id


def record_gap(
    connection: sqlite3.Connection,
    answer_id: str,
    routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the gap for a question the record did not settle.

    The question itself is not passed in: it is on the answer row this gap
    points at, and a read joins it back on.

    Args:
        connection: An open capture connection.
        answer_id: The answer this gap was detected on.
        routing: Who to ask, as the response carries it, or None when there
            was nobody to suggest.

    Returns:
        The gap as a read would return it.

    Raises:
        UnknownAnswerError: If no answer has that id.
    """
    row_id = _insert(
        connection,
        answer_id,
        "INSERT INTO gaps (answer_id, routing) VALUES (?, ?)",
        (answer_id, None if routing is None else json.dumps(routing)),
    )
    return _one(connection, gaps, row_id)


def record_correction(
    connection: sqlite3.Connection,
    answer_id: str,
    what_was_wrong: str,
    what_is_right: str,
) -> dict[str, Any]:
    """Write what a user says an answer got wrong.

    Args:
        connection: An open capture connection.
        answer_id: The answer being corrected.
        what_was_wrong: What the answer claimed that it should not have.
        what_is_right: What the user says is true instead.

    Returns:
        The correction as a read would return it.

    Raises:
        UnknownAnswerError: If no answer has that id.
    """
    row_id = _insert(
        connection,
        answer_id,
        "INSERT INTO corrections (answer_id, what_was_wrong, what_is_right) "
        "VALUES (?, ?, ?)",
        (answer_id, what_was_wrong, what_is_right),
    )
    return _one(connection, corrections, row_id)


def record_feedback(
    connection: sqlite3.Connection,
    answer_id: str,
    verdict: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Write a verdict on an answer.

    Args:
        connection: An open capture connection.
        answer_id: The answer being judged.
        verdict: ``"up"`` or ``"down"``.
        note: Anything the user wanted to add, or None.

    Returns:
        The feedback as a read would return it.

    Raises:
        UnknownAnswerError: If no answer has that id.
        ValueError: If the verdict is not one of :data:`VERDICTS`.
    """
    if verdict not in VERDICTS:
        raise ValueError(
            f"verdict must be one of {', '.join(VERDICTS)}, not {verdict!r}"
        )
    row_id = _insert(
        connection,
        answer_id,
        "INSERT INTO feedback (answer_id, verdict, note) VALUES (?, ?, ?)",
        (answer_id, verdict, note),
    )
    return _one(connection, feedback, row_id)


def gaps(
    connection: sqlite3.Connection,
    limit: int = DEFAULT_RECORDS,
    row_id: int | None = None,
) -> list[dict[str, Any]]:
    """Read gaps back, most recent first.

    Args:
        connection: An open capture connection.
        limit: How many to return at most.
        row_id: One gap to return instead of the most recent ones. Used to
            hand a freshly written row back to its writer.

    Returns:
        Each gap with the question that produced it, the answer that was
        given, and the routing suggestion when there was one.
    """
    rows = _select(connection, "gaps", "g.routing", limit, row_id)
    return [_record(row) | {"routing": _loaded(row["routing"])} for row in rows]


def corrections(
    connection: sqlite3.Connection,
    limit: int = DEFAULT_RECORDS,
    row_id: int | None = None,
) -> list[dict[str, Any]]:
    """Read corrections back, most recent first.

    Args:
        connection: An open capture connection.
        limit: How many to return at most.
        row_id: One correction to return instead of the most recent ones.

    Returns:
        Each correction with the question and answer it was written against.
    """
    rows = _select(
        connection, "corrections", "g.what_was_wrong, g.what_is_right", limit, row_id
    )
    return [
        _record(row)
        | {
            "what_was_wrong": row["what_was_wrong"],
            "what_is_right": row["what_is_right"],
        }
        for row in rows
    ]


def feedback(
    connection: sqlite3.Connection,
    limit: int = DEFAULT_RECORDS,
    row_id: int | None = None,
) -> list[dict[str, Any]]:
    """Read feedback back, most recent first.

    Args:
        connection: An open capture connection.
        limit: How many to return at most.
        row_id: One verdict to return instead of the most recent ones.

    Returns:
        Each verdict with the question and answer it was given on.
    """
    rows = _select(connection, "feedback", "g.verdict, g.note", limit, row_id)
    return [
        _record(row) | {"verdict": row["verdict"], "note": row["note"]} for row in rows
    ]


def record(connection: sqlite3.Connection, kind: str, row_id: int) -> dict[str, Any]:
    """Read one gap, correction, or piece of feedback by its id.

    Args:
        connection: An open capture connection.
        kind: Which kind it is, one of :data:`KINDS`.
        row_id: Its id.

    Returns:
        The record as a list of that kind would return it.

    Raises:
        UnknownRecordError: If no record of that kind has that id.
        ValueError: If ``kind`` is not one of :data:`KINDS`.
    """
    rows = _READERS[_kind(kind)](connection, row_id=row_id)
    if not rows:
        raise UnknownRecordError(f"no {kind} record has id {row_id}")
    [row] = rows
    return row


def mark_reviewed(
    connection: sqlite3.Connection,
    kind: str,
    row_id: int,
    reviewed: bool = True,
) -> dict[str, Any]:
    """Mark one record seen, or put it back among the new ones.

    Marking a record that is already reviewed keeps the time it was first
    marked, so repeating the request does not move it.

    Args:
        connection: An open capture connection.
        kind: Which kind it is, one of :data:`KINDS`.
        row_id: Its id.
        reviewed: True to mark it reviewed, False to clear the mark.

    Returns:
        The record as a read of it would return it afterwards.

    Raises:
        UnknownRecordError: If no record of that kind has that id.
        ValueError: If ``kind`` is not one of :data:`KINDS`.
    """
    table = _kind(kind)
    if reviewed:
        stamp = "coalesce(reviewed_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
    else:
        stamp = "NULL"
    with connection:
        cursor = connection.execute(
            f"UPDATE {table} SET reviewed_at = {stamp} WHERE id = ?", (row_id,)
        )
    if cursor.rowcount == 0:
        raise UnknownRecordError(f"no {kind} record has id {row_id}")
    return record(connection, table, row_id)


def _kind(kind: str) -> str:
    """Check that a kind names one of the three record tables.

    Args:
        kind: What the caller named.

    Returns:
        The kind, unchanged.

    Raises:
        ValueError: If it is not one of :data:`KINDS`.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}")
    return kind


def _insert(
    connection: sqlite3.Connection,
    answer_id: str,
    statement: str,
    parameters: tuple[Any, ...],
) -> int:
    """Write one row against an answer, refusing an id that is not there.

    Foreign keys are on, so an unknown id fails at the write rather than
    being stored as an orphan. What SQLite raises for that is the same
    exception it raises for any other constraint, so the id is checked
    afterwards to say which of the two happened in the words of this domain.

    Args:
        connection: An open capture connection.
        answer_id: The answer the row points at.
        statement: The INSERT to run.
        parameters: Its parameters.

    Returns:
        The new row's id.

    Raises:
        UnknownAnswerError: If no answer has that id.
    """
    try:
        with connection:
            cursor = connection.execute(statement, parameters)
    except sqlite3.IntegrityError:
        if not _answer_exists(connection, answer_id):
            raise UnknownAnswerError(
                f"no answer with id {answer_id!r}. A record has to point at "
                f"an answer this service gave; the id comes back on the "
                f"response to /answer."
            ) from None
        raise
    return int(cursor.lastrowid)


def _answer_exists(connection: sqlite3.Connection, answer_id: str) -> bool:
    """Return whether an answer row has that id.

    Args:
        connection: An open capture connection.
        answer_id: The id to look for.

    Returns:
        Whether the row is there.
    """
    return (
        connection.execute(
            "SELECT count(*) FROM answers WHERE id = ?", (answer_id,)
        ).fetchone()[0]
        > 0
    )


def _select(
    connection: sqlite3.Connection,
    table: str,
    columns: str,
    limit: int,
    row_id: int | None,
) -> list[sqlite3.Row]:
    """Read rows of one kind, joined to the answers they hang off.

    The join is what makes a row readable without a second call: the reader
    of a gap wants the answer that was given, not an id to go and look up.

    Args:
        connection: An open capture connection.
        table: Which of the three tables to read. Not caller-supplied — the
            three call sites name it — so it is interpolated where a
            parameter cannot go.
        columns: The table's own columns to select, already aliased to
            ``g``.
        limit: How many rows to return at most.
        row_id: One row to return instead of the most recent ones.

    Returns:
        The rows, most recent first, or the single row that was named.
    """
    shared = (
        f"SELECT g.id, g.answer_id, g.created_at, g.reviewed_at, {columns}, "
        f"a.thread_id, a.query AS answer_query, a.answer, a.citations, "
        f"a.abstained "
        f"FROM {table} AS g JOIN answers AS a ON a.id = g.answer_id"
    )
    if row_id is not None:
        return connection.execute(f"{shared} WHERE g.id = ?", (row_id,)).fetchall()
    # The id breaks ties. Timestamps are recorded to the millisecond, and two
    # rows written inside one are still ordered by which was written first.
    return connection.execute(
        f"{shared} ORDER BY g.created_at DESC, g.id DESC LIMIT ?", (limit,)
    ).fetchall()


def _one(
    connection: sqlite3.Connection,
    read: Any,
    row_id: int,
) -> dict[str, Any]:
    """Read one freshly written row back through its own reader.

    A write returns exactly what a read of it would, rather than an
    assembled copy that could drift from it.

    Args:
        connection: An open capture connection.
        read: The reader for this kind of record.
        row_id: The row to return.

    Returns:
        The row.
    """
    [row] = read(connection, row_id=row_id)
    return row


def _record(row: sqlite3.Row) -> dict[str, Any]:
    """Build what every kind of record carries.

    Args:
        row: One joined row.

    Returns:
        The row's own identity, timestamp, and review state, plus the
        question, answer, and citations it hangs off.
    """
    return {
        "id": row["id"],
        "answer_id": row["answer_id"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
        "thread_id": row["thread_id"],
        "question": row["answer_query"],
        "answer": row["answer"],
        "citations": json.loads(row["citations"]),
        "abstained": bool(row["abstained"]),
    }


def _loaded(value: str | None) -> dict[str, Any] | None:
    """Parse a JSON column that may be null.

    Args:
        value: The stored JSON, or None.

    Returns:
        The parsed object, or None.
    """
    return None if value is None else json.loads(value)


#: The reader for each kind of record. Defined after the readers themselves,
#: which is the only reason it sits at the bottom of the module.
_READERS = {"gaps": gaps, "corrections": corrections, "feedback": feedback}
