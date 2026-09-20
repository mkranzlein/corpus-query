"""Tests for reading prior-meeting summaries out of the document store.

The store's own schema lands separately; these tests create the small part of
it this read depends on, so a shape change there shows up here as a failure
rather than as a silently empty prompt.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from corpus_query.transcripts.summaries import (
    NO_PRIOR_MEETINGS,
    PriorMeeting,
    describe_prior_meetings,
    read_summaries,
)

DOCUMENTS = """
    CREATE TABLE documents (
        slug TEXT PRIMARY KEY,
        subject TEXT NOT NULL,
        date TEXT NOT NULL,
        summary TEXT
    )
"""


def make_store(path: Path, rows: list[tuple[str, str, str, str | None]]) -> Path:
    """Create a database holding just enough of a ``documents`` table.

    Args:
        path: Where to write the database.
        rows: ``(slug, subject, date, summary)`` per document.

    Returns:
        The path written.
    """
    with sqlite3.connect(path) as connection:
        connection.execute(DOCUMENTS)
        connection.executemany("INSERT INTO documents VALUES (?, ?, ?, ?)", rows)
    return path


def test_a_missing_database_is_not_an_error(tmp_path: Path):
    assert read_summaries(tmp_path / "nothing-here.db") == ()


def test_a_database_without_a_documents_table_is_not_an_error(tmp_path: Path):
    path = tmp_path / "corpus.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
    assert read_summaries(path) == ()


def test_summaries_come_back_oldest_first(tmp_path: Path):
    path = make_store(
        tmp_path / "corpus.db",
        [
            ("later", "Pricing review", "2026-04-02", "Settled the discount floor."),
            ("earlier", "Rev B schedule", "2026-02-11", "Held the rev B date."),
        ],
    )
    summaries = read_summaries(path)
    assert [meeting.subject for meeting in summaries] == [
        "Rev B schedule",
        "Pricing review",
    ]
    assert summaries[0].summary == "Held the rev B date."


def test_an_unsummarized_document_is_skipped(tmp_path: Path):
    path = make_store(
        tmp_path / "corpus.db",
        [
            ("a", "Ingested but not enriched", "2026-01-08", None),
            ("b", "Blank summary", "2026-01-09", "   "),
            ("c", "Summarized", "2026-01-10", "Agreed the launch date."),
        ],
    )
    assert [meeting.subject for meeting in read_summaries(path)] == ["Summarized"]


def test_reading_does_not_create_a_database(tmp_path: Path):
    path = tmp_path / "corpus.db"
    read_summaries(path)
    assert not path.exists()


def test_the_first_batch_is_told_there_is_nothing_yet():
    assert describe_prior_meetings(()) == NO_PRIOR_MEETINGS


def test_prior_meetings_are_described_with_subject_date_and_summary():
    described = describe_prior_meetings(
        (PriorMeeting("Rev B schedule", "2026-02-11", "Held the rev B date."),)
    )
    assert "Rev B schedule" in described
    assert "2026-02-11" in described
    assert "Held the rev B date." in described
