"""Storing spans in the usage database, and reading them back.

A span is one timed step of answering a question — a model call, a search, a
rerank — and a trace is every span one question produced. They are written
here by :mod:`corpus_query.tracing`, as rows in the same local, uncommitted
file that holds the graph checkpoints and the captured records, so looking at
how a query ran is a SQL query rather than a tracing service to stand up.
See :mod:`corpus_query.store.usage` for why that file is not the corpus.

This module knows about rows and nothing about OpenTelemetry. Turning an SDK
span into a row is the exporter's job; this one owns the tables.

Why the schema version is a row
===============================

The usage database is shared: LangGraph's checkpointer keeps its tables here,
and so does :mod:`corpus_query.store.capture`. Neither owns the file, so
neither sets ``PRAGMA user_version``, and neither does this module. The
version of these tables lives in ``spans_meta``, a table they own, the same
way ``capture_meta`` versions the captured records. Each writer in a shared
file versions its own tables; nothing versions the file.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from corpus_query.store.usage import usage_database

#: The version of these tables this code reads and writes. Recorded in
#: ``spans_meta`` rather than the ``user_version`` pragma; see the module
#: docstring.
SCHEMA_VERSION = 1

#: The key the version is stored under in ``spans_meta``.
SCHEMA_VERSION_KEY = "schema_version"

#: How long a write waits for another writer to finish with the file before
#: giving up, in seconds. Spans are written off the event loop, by a thread
#: that nothing waits on, so waiting a while costs nothing; failing costs the
#: spans.
BUSY_TIMEOUT_SECONDS = 30.0

_SCHEMA_PATH = Path(__file__).parent / "spans.sql"


class SpansSchemaVersionError(Exception):
    """The span tables are at a version this code does not know."""


@dataclass(frozen=True)
class SpanRow:
    """One span, as it is stored."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: str
    start_time_unix_nano: int
    end_time_unix_nano: int
    status_code: str
    status_message: str | None
    attributes: dict[str, Any]
    events: list[dict[str, Any]]
    scope: str


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the usage database and make sure these tables are in it.

    Args:
        path: Where the usage database lives, or None for the project's
            default. The file and its directory are created if missing.

    Returns:
        An open connection, with rows returned as :class:`sqlite3.Row`.

    Raises:
        SpansSchemaVersionError: If the file already holds these tables at a
            version this code does not know how to work with.
    """
    connection = sqlite3.connect(usage_database(path), timeout=BUSY_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    try:
        _initialize(connection)
    except BaseException:
        connection.close()
        raise
    return connection


def _initialize(connection: sqlite3.Connection) -> None:
    """Create these tables, or check the version of the ones already there.

    Creating them is one transaction with the version row, so two writers
    opening a fresh file at once cannot leave it with the tables and no
    version: the second waits for the first, then finds the tables there.

    Args:
        connection: An open connection.

    Raises:
        SpansSchemaVersionError: If the recorded version is not
            :data:`SCHEMA_VERSION`.
    """
    if not _has_tables(connection):
        # An explicit BEGIN IMMEDIATE takes the write lock before looking
        # again, and executescript would otherwise commit on its own.
        connection.execute("BEGIN IMMEDIATE")
        try:
            if not _has_tables(connection):
                for statement in _statements(_SCHEMA_PATH.read_text("utf-8")):
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO spans_meta (key, value) VALUES (?, ?)",
                    (SCHEMA_VERSION_KEY, str(SCHEMA_VERSION)),
                )
        except BaseException:
            connection.rollback()
            raise
        connection.commit()
    version = _recorded_version(connection)
    if version != SCHEMA_VERSION:
        raise SpansSchemaVersionError(
            f"the spans in this usage database are at version {version}, but "
            f"this code only knows how to work with version {SCHEMA_VERSION}. "
            f"The usage database is local and not committed, so deleting it "
            f"is a supported way out — it costs the conversations, records, "
            f"and traces it held and nothing else."
        )


def _statements(script: str) -> list[str]:
    """Split the schema into statements, dropping its comments.

    :meth:`sqlite3.Connection.executescript` would do this, but it commits
    any open transaction first, which would undo the point of opening one.

    Args:
        script: The schema file's text.

    Returns:
        Each statement, without its terminating semicolon.
    """
    lines = [line for line in script.splitlines() if not line.lstrip().startswith("--")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


def _has_tables(connection: sqlite3.Connection) -> bool:
    """Return whether ``spans_meta`` is already in the file."""
    return (
        connection.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'spans_meta'"
        ).fetchone()[0]
        > 0
    )


def _recorded_version(connection: sqlite3.Connection) -> int | None:
    """Read the version recorded alongside these tables.

    Returns:
        The version, or None when the row is missing or not a number —
        a file written by something other than this module.
    """
    row = connection.execute(
        "SELECT value FROM spans_meta WHERE key = ?", (SCHEMA_VERSION_KEY,)
    ).fetchone()
    try:
        return None if row is None else int(row["value"])
    except ValueError:
        return None


def write(connection: sqlite3.Connection, rows: Iterable[SpanRow]) -> int:
    """Write spans, in one transaction.

    Args:
        connection: An open connection from :func:`connect`.
        rows: The spans to write.

    Returns:
        How many were written.
    """
    values = [
        (
            row.trace_id,
            row.span_id,
            row.parent_span_id,
            row.name,
            row.kind,
            row.start_time_unix_nano,
            row.end_time_unix_nano,
            row.status_code,
            row.status_message,
            json.dumps(row.attributes),
            json.dumps(row.events),
            row.scope,
        )
        for row in rows
    ]
    with connection:
        connection.executemany(
            "INSERT OR REPLACE INTO spans (trace_id, span_id, parent_span_id, "
            "name, kind, start_time_unix_nano, end_time_unix_nano, status_code, "
            "status_message, attributes, events, scope) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
    return len(values)


def trace(connection: sqlite3.Connection, trace_id: str) -> list[SpanRow]:
    """Read every span of one trace, in the order they started.

    Args:
        connection: An open connection from :func:`connect`.
        trace_id: The trace, as 32 hex digits.

    Returns:
        The spans, earliest first. Empty for a trace nothing was written
        under.
    """
    rows = connection.execute(
        "SELECT * FROM spans WHERE trace_id = ? ORDER BY start_time_unix_nano, rowid",
        (trace_id,),
    ).fetchall()
    return [_row(row) for row in rows]


def traces(connection: sqlite3.Connection) -> list[str]:
    """List the traces written, most recent first.

    Args:
        connection: An open connection from :func:`connect`.

    Returns:
        Trace ids, ordered by when each trace's first span started.
    """
    rows = connection.execute(
        "SELECT trace_id FROM spans GROUP BY trace_id "
        "ORDER BY min(start_time_unix_nano) DESC"
    ).fetchall()
    return [row["trace_id"] for row in rows]


def _row(row: sqlite3.Row) -> SpanRow:
    """Build a span from a stored row."""
    return SpanRow(
        trace_id=row["trace_id"],
        span_id=row["span_id"],
        parent_span_id=row["parent_span_id"],
        name=row["name"],
        kind=row["kind"],
        start_time_unix_nano=row["start_time_unix_nano"],
        end_time_unix_nano=row["end_time_unix_nano"],
        status_code=row["status_code"],
        status_message=row["status_message"],
        attributes=json.loads(row["attributes"]),
        events=json.loads(row["events"]),
        scope=row["scope"],
    )
