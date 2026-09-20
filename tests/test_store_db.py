"""Tests for the document store schema and connection handling."""

from __future__ import annotations

import sqlite3

import pytest

from corpus_query.store.db import SCHEMA_VERSION, SchemaVersionError, connect
from corpus_query.store.kinds import CHUNK_KINDS, SOURCE_KINDS


def _insert_document(connection: sqlite3.Connection, slug: str = "meeting-1") -> int:
    """Insert a minimal document row and return its id."""
    cursor = connection.execute(
        """
        INSERT INTO documents
            (slug, source_path, source_kind, title, document_date)
        VALUES (?, ?, 'transcript', ?, ?)
        """,
        (slug, f"transcripts/{slug}.md", "Weekly sync", "2026-01-05"),
    )
    connection.commit()
    return cursor.lastrowid


def _insert_chunk(
    connection: sqlite3.Connection,
    document_id: int,
    ordinal: int = 0,
    text: str = "Priya opened the meeting and reviewed the roadmap.",
) -> int:
    """Insert a minimal chunk row and return its id."""
    cursor = connection.execute(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, word_count, location,
             span_start, span_end, kind)
        VALUES (?, ?, ?, ?, 'turns 0-2', ?, ?, 'turn_window')
        """,
        (document_id, ordinal, text, len(text.split()), 0, 2),
    )
    connection.commit()
    return cursor.lastrowid


def test_schema_applies_to_a_fresh_in_memory_database():
    connection = connect(":memory:")
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "documents",
        "attendees",
        "chunks",
        "topics",
        "document_topics",
    } <= tables


def test_opening_records_the_schema_version():
    connection = connect(":memory:")
    (version,) = connection.execute("PRAGMA user_version").fetchone()
    assert version == SCHEMA_VERSION


def test_opening_a_future_version_fails_loudly(tmp_path):
    path = tmp_path / "future.db"
    connect(path).close()
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()

    with pytest.raises(SchemaVersionError):
        connect(path)


def test_reopening_an_existing_database_does_not_reapply_the_schema(tmp_path):
    path = tmp_path / "store.db"
    connect(path).close()

    connection = connect(path)
    document_id = _insert_document(connection)
    connection.close()

    connection = connect(path)
    row = connection.execute(
        "SELECT slug FROM documents WHERE id = ?", (document_id,)
    ).fetchone()
    assert row["slug"] == "meeting-1"


def test_chunk_insert_is_findable_through_fts():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    _insert_chunk(connection, document_id, text="Priya reviewed the roadmap.")

    rows = connection.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'roadmap'"
    ).fetchall()
    assert len(rows) == 1


def test_chunk_update_keeps_fts_in_step():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    chunk_id = _insert_chunk(connection, document_id, text="Talked about hardware.")

    connection.execute(
        "UPDATE chunks SET text = ? WHERE id = ?",
        ("Talked about software instead.", chunk_id),
    )
    connection.commit()

    assert not connection.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'hardware'"
    ).fetchall()
    assert connection.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'software'"
    ).fetchall()


def test_chunk_delete_keeps_fts_in_step():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    chunk_id = _insert_chunk(
        connection, document_id, text="A one-off mention of budget."
    )

    connection.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))
    connection.commit()

    assert not connection.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'budget'"
    ).fetchall()


def test_foreign_key_violation_is_rejected():
    connection = connect(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO chunks
                (document_id, ordinal, text, word_count, location,
                 span_start, span_end, kind)
            VALUES (999, 0, 'orphan', 1, 'turn 0', 0, 0, 'turn_window')
            """
        )


def test_cascading_delete_leaves_nothing_orphaned():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    chunk_id = _insert_chunk(connection, document_id)
    connection.execute(
        "INSERT INTO attendees (document_id, name) VALUES (?, ?)",
        (document_id, "Priya"),
    )
    connection.execute("INSERT INTO topics (name) VALUES ('Hardware')")
    connection.execute(
        "INSERT INTO document_topics (document_id, topic_id) VALUES (?, 1)",
        (document_id,),
    )
    connection.commit()

    connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    connection.commit()

    assert not connection.execute("SELECT 1 FROM chunks").fetchall()
    assert not connection.execute("SELECT 1 FROM attendees").fetchall()
    assert not connection.execute("SELECT 1 FROM document_topics").fetchall()
    assert not connection.execute(
        "SELECT rowid FROM chunks_fts WHERE rowid = ?", (chunk_id,)
    ).fetchall()
    # The topic itself is not document-scoped, so it survives.
    assert connection.execute("SELECT 1 FROM topics").fetchall()


def test_chunk_id_is_not_reused_after_delete():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    first_id = _insert_chunk(connection, document_id, ordinal=0)
    connection.execute("DELETE FROM chunks WHERE id = ?", (first_id,))
    connection.commit()

    second_id = _insert_chunk(connection, document_id, ordinal=0)
    assert second_id != first_id


def test_topic_name_uniqueness_is_enforced():
    connection = connect(":memory:")
    connection.execute("INSERT INTO topics (name) VALUES ('Hardware')")
    connection.commit()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO topics (name) VALUES ('Hardware')")


def test_document_slug_uniqueness_is_enforced():
    connection = connect(":memory:")
    _insert_document(connection, slug="meeting-1")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_document(connection, slug="meeting-1")


def test_a_summary_chunk_has_no_span():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    cursor = connection.execute(
        """
        INSERT INTO chunks (document_id, ordinal, text, word_count, location, kind)
        VALUES (?, ?, ?, ?, 'summary', 'summary')
        """,
        (document_id, 99, "The team held the rev B date.", 6),
    )
    connection.commit()
    row = connection.execute(
        "SELECT span_start, span_end FROM chunks WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    assert row["span_start"] is None
    assert row["span_end"] is None


def test_a_summary_chunk_may_not_claim_a_span():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO chunks
                (document_id, ordinal, text, word_count, location,
                 span_start, span_end, kind)
            VALUES (?, ?, ?, ?, 'summary', ?, ?, 'summary')
            """,
            (document_id, 99, "A summary.", 2, 0, 4),
        )


def test_a_turn_window_needs_a_span():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO chunks
                (document_id, ordinal, text, word_count, location, kind)
            VALUES (?, ?, ?, ?, 'turn 1', 'turn_window')
            """,
            (document_id, 1, "Something said.", 2),
        )


def test_a_span_may_not_run_backwards():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO chunks
                (document_id, ordinal, text, word_count, location,
                 span_start, span_end, kind)
            VALUES (?, ?, ?, ?, 'turns 4-0', 4, 0, 'turn_window')
            """,
            (document_id, 1, "Something said.", 2),
        )


def test_every_chunk_kind_the_code_names_is_one_the_schema_accepts():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    for ordinal, kind in enumerate(CHUNK_KINDS):
        connection.execute(
            """
            INSERT INTO chunks
                (document_id, ordinal, text, word_count, location,
                 span_start, span_end, kind)
            VALUES (?, ?, 'some text', 2, 'somewhere', ?, ?, ?)
            """,
            (document_id, ordinal, None, None, kind)
            if kind in ("summary", "sheet_summary")
            else (document_id, ordinal, 0, 0, kind),
        )
    connection.commit()
    assert len(connection.execute("SELECT id FROM chunks").fetchall()) == len(
        CHUNK_KINDS
    )


def test_a_chunk_kind_the_code_does_not_name_is_rejected():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO chunks
                (document_id, ordinal, text, word_count, location,
                 span_start, span_end, kind)
            VALUES (?, 0, 'some text', 2, 'somewhere', 0, 0, 'paragraph')
            """,
            (document_id,),
        )


def test_every_source_kind_the_code_names_is_one_the_schema_accepts():
    connection = connect(":memory:")
    for index, kind in enumerate(SOURCE_KINDS):
        connection.execute(
            """
            INSERT INTO documents
                (slug, source_path, source_kind, title, document_date)
            VALUES (?, 'somewhere', ?, 'Something', '2026-01-05')
            """,
            (f"document-{index}", kind),
        )
    connection.commit()
    assert len(connection.execute("SELECT id FROM documents").fetchall()) == len(
        SOURCE_KINDS
    )


def test_a_source_kind_the_code_does_not_name_is_rejected():
    connection = connect(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO documents
                (slug, source_path, source_kind, title, document_date)
            VALUES ('odt', 'somewhere', 'odt', 'Something', '2026-01-05')
            """
        )


def test_an_author_is_optional_so_the_two_mechanisms_coexist():
    connection = connect(":memory:")
    _insert_document(connection, slug="weekly-sync")
    connection.execute("INSERT INTO attendees (document_id, name) VALUES (1, 'Priya')")
    connection.execute(
        """
        INSERT INTO documents
            (slug, source_path, source_kind, title, document_date, author)
        VALUES ('spec', 'somewhere', 'docx', 'Thermal spec', '2026-01-05', 'Devon')
        """
    )
    connection.commit()
    rows = connection.execute(
        "SELECT slug, author FROM documents ORDER BY slug"
    ).fetchall()
    assert [(row["slug"], row["author"]) for row in rows] == [
        ("spec", "Devon"),
        ("weekly-sync", None),
    ]
    assert connection.execute("SELECT name FROM attendees").fetchall()


def test_an_embedding_carries_the_model_that_made_it():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    chunk_id = _insert_chunk(connection, document_id)
    connection.execute(
        """
        UPDATE chunks
        SET embedding = ?, embedding_model = ?, embedding_dim = ?
        WHERE id = ?
        """,
        (b"\x00\x01", "BAAI/bge-small-en-v1.5", 384, chunk_id),
    )
    connection.commit()
    row = connection.execute(
        "SELECT embedding_model, embedding_dim FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()
    assert row["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert row["embedding_dim"] == 384


def test_an_embedding_without_its_model_is_rejected():
    connection = connect(":memory:")
    document_id = _insert_document(connection)
    chunk_id = _insert_chunk(connection, document_id)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE chunks SET embedding = ? WHERE id = ?", (b"\x00\x01", chunk_id)
        )
