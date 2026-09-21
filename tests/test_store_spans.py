"""Tests for the span tables in the usage database.

The file is shared with the graph checkpoints and the captured records, so
what is worth proving is that these tables version themselves without
claiming the file, and that they sit beside the others without disturbing
them.
"""

from __future__ import annotations

import sqlite3

import pytest

from corpus_query.store import capture, spans
from corpus_query.store.spans import SpanRow, SpansSchemaVersionError


def a_span(**overrides) -> SpanRow:
    """Build one span with every field populated."""
    fields = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "parent_span_id": None,
        "name": "invoke_agent corpus-query",
        "kind": "INTERNAL",
        "start_time_unix_nano": 1_000,
        "end_time_unix_nano": 2_000,
        "status_code": "UNSET",
        "status_message": None,
        "attributes": {"gen_ai.operation.name": "invoke_agent", "counts": [1, 2]},
        "events": [],
        "scope": "corpus_query",
    }
    return SpanRow(**(fields | overrides))


def test_connecting_creates_the_tables_and_records_their_version(tmp_path) -> None:
    """The version is a row these tables own, and the file's pragma is untouched."""
    database = tmp_path / "usage.db"
    connection = spans.connect(database)
    try:
        (version,) = connection.execute(
            "SELECT value FROM spans_meta WHERE key = 'schema_version'"
        ).fetchone()
        (user_version,) = connection.execute("PRAGMA user_version").fetchone()
    finally:
        connection.close()

    assert version == str(spans.SCHEMA_VERSION)
    assert user_version == 0


def test_the_tables_sit_beside_the_captured_records(tmp_path) -> None:
    """Either store can be opened first, and each finds its own tables."""
    database = tmp_path / "usage.db"
    capture.connect(database).close()
    spans.connect(database).close()
    capture.connect(database).close()

    connection = sqlite3.connect(database)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert {"spans", "spans_meta", "answers", "capture_meta"} <= tables


def test_a_version_this_code_does_not_know_is_refused(tmp_path) -> None:
    """A file from a later release is reported, not written into."""
    database = tmp_path / "usage.db"
    spans.connect(database).close()
    connection = sqlite3.connect(database)
    connection.execute("UPDATE spans_meta SET value = '99'")
    connection.commit()
    connection.close()

    with pytest.raises(SpansSchemaVersionError, match="version 99"):
        spans.connect(database)


def test_a_written_trace_reads_back_whole_and_in_order(tmp_path) -> None:
    """Attributes and events round-trip, and spans come back by start time."""
    connection = spans.connect(tmp_path / "usage.db")
    try:
        root = a_span()
        child = a_span(
            span_id="c" * 16,
            parent_span_id="b" * 16,
            name="chat granite4.1:8b",
            start_time_unix_nano=1_500,
            status_code="ERROR",
            status_message="boom",
            events=[{"name": "exception", "attributes": {"exception.type": "X"}}],
        )
        other = a_span(trace_id="d" * 32, start_time_unix_nano=5_000)
        assert spans.write(connection, [child, root, other]) == 3

        assert spans.trace(connection, "a" * 32) == [root, child]
        assert spans.traces(connection) == ["d" * 32, "a" * 32]
        assert spans.trace(connection, "f" * 32) == []
    finally:
        connection.close()
