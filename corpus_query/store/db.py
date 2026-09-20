"""Opening the document store.

The document store is a single SQLite file. This module is the only place
that knows how to create one, bring an empty file up to the current schema,
and refuse to open one written by a newer version of this code than the one
running.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

#: The schema version this code knows how to read and write. Stored in the
#: database file's ``user_version`` pragma, which SQLite reserves for exactly
#: this purpose and does not use itself.
SCHEMA_VERSION = 1

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class SchemaVersionError(Exception):
    """A database's recorded schema version does not match this code's."""


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a document store, creating and initializing it if needed.

    Args:
        path: Where the database file lives. ``:memory:`` opens a private
            in-memory database, mainly for tests. A path that does not exist
            yet is created.

    Returns:
        An open connection with foreign key enforcement on and rows
        returned as ``sqlite3.Row``.

    Raises:
        SchemaVersionError: If the database's recorded schema version is not
            the one this code knows how to work with.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    # Off by default in SQLite, and scoped to the connection rather than the
    # file, so it has to be set every time one is opened.
    connection.execute("PRAGMA foreign_keys = ON")
    _initialize(connection)
    return connection


def _initialize(connection: sqlite3.Connection) -> None:
    """Apply the schema to a fresh database, or check an existing one's.

    Args:
        connection: An open connection, with foreign keys already enabled.

    Raises:
        SchemaVersionError: If the database already has a ``user_version``
            other than 0 (uninitialized) or ``SCHEMA_VERSION``.
    """
    (version,) = connection.execute("PRAGMA user_version").fetchone()
    if version == 0 and _is_empty(connection):
        connection.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
    elif version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"This database is at schema version {version}, but this code "
            f"only knows how to work with version {SCHEMA_VERSION}. "
            f"{'Open it with a newer version of this code.' if version > SCHEMA_VERSION else 'There is no migration path from it yet.'}"
        )


def _is_empty(connection: sqlite3.Connection) -> bool:
    """Return whether a database has no user tables yet.

    A ``user_version`` of 0 is also SQLite's default for a database that was
    never touched by this code, so it is checked against the sqlite_master
    table rather than trusted on its own.

    Args:
        connection: An open connection.

    Returns:
        True if the database holds no tables.
    """
    (count,) = connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
    ).fetchone()
    return count == 0
