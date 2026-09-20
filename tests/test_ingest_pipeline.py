"""Tests for reading documents and writing them into the document store."""

from __future__ import annotations

import sqlite3

import pytest

from corpus_query.ingest import transcripts
from corpus_query.ingest.chunk import Chunk
from corpus_query.ingest.pipeline import (
    document_paths,
    ingest_file,
    ingest_paths,
    reader_for,
)
from corpus_query.ingest.reader import IngestError
from corpus_query.store.db import connect
from corpus_query.store.kinds import TRANSCRIPT, TURN_WINDOW
from corpus_query.transcripts.render import render_meeting


@pytest.fixture
def store():
    """Return an open, empty document store."""
    connection = connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def write_transcript(tmp_path, make_meeting):
    """Return a factory that writes a rendered transcript to a file."""

    def factory(slug: str = "rev-b-schedule", **overrides):
        path = tmp_path / f"{slug}.md"
        path.write_text(render_meeting(make_meeting(**overrides)), encoding="utf-8")
        return path

    return factory


def rows(connection: sqlite3.Connection, sql: str, *parameters) -> list[sqlite3.Row]:
    """Run a query and return every row."""
    return connection.execute(sql, parameters).fetchall()


def test_a_transcript_becomes_a_document_row(store, write_transcript):
    result = ingest_file(store, write_transcript())
    row = rows(store, "SELECT * FROM documents")[0]
    assert row["slug"] == "rev-b-schedule"
    assert row["source_kind"] == TRANSCRIPT
    assert row["title"] == "Rev B schedule"
    assert row["document_date"] == "2026-03-04"
    assert row["id"] == result.document_id
    assert not result.replaced


def test_a_transcript_has_no_author_but_has_attendees(store, write_transcript):
    ingest_file(store, write_transcript())
    assert rows(store, "SELECT author FROM documents")[0]["author"] is None
    assert len(rows(store, "SELECT id FROM attendees")) == 3


def test_a_transcript_is_ingested_by_the_transcript_reader(write_transcript):
    assert reader_for(write_transcript()) is transcripts.read_transcript


def test_a_file_no_reader_claims_is_an_error(tmp_path):
    with pytest.raises(IngestError):
        reader_for(tmp_path / "budget.numbers")


def test_the_source_path_is_recorded(store, write_transcript):
    path = write_transcript()
    ingest_file(store, path)
    assert rows(store, "SELECT source_path FROM documents")[0][0] == str(path)


def test_attendees_are_rows_including_one_who_never_speaks(store, write_transcript):
    ingest_file(store, write_transcript())
    names = {row["name"] for row in rows(store, "SELECT name FROM attendees")}
    assert names == {"Priya", "Marcus", "Sofia"}


def test_chunks_are_written_as_turn_windows(store, write_transcript):
    result = ingest_file(store, write_transcript())
    chunks = rows(store, "SELECT * FROM chunks ORDER BY ordinal")
    assert len(chunks) == result.chunks
    assert [chunk["ordinal"] for chunk in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert chunk["kind"] == TURN_WINDOW
        assert chunk["span_start"] is not None
        assert chunk["span_end"] is not None
        assert chunk["word_count"] == len(chunk["text"].split())


def test_a_chunk_carries_a_citation_label_naming_its_turns(store, write_transcript):
    ingest_file(store, write_transcript())
    chunk = rows(store, "SELECT * FROM chunks ORDER BY ordinal")[0]
    assert chunk["location"] == f"turns {chunk['span_start']}-{chunk['span_end']}"


def test_chunk_text_is_byte_identical_to_the_file(store, write_transcript):
    path = write_transcript()
    ingest_file(store, path)
    source = path.read_text(encoding="utf-8")
    for chunk in rows(store, "SELECT text FROM chunks"):
        assert chunk["text"] in source


def test_a_word_from_the_transcript_finds_its_chunk(store, write_transcript):
    ingest_file(store, write_transcript())
    found = rows(
        store,
        """
        SELECT chunks.text FROM chunks_fts
        JOIN chunks ON chunks.id = chunks_fts.rowid
        WHERE chunks_fts MATCH 'connectors'
        """,
    )
    assert found
    assert "connectors" in found[0]["text"]


def test_ingesting_twice_replaces_rather_than_duplicates(store, write_transcript):
    path = write_transcript()
    ingest_file(store, path)
    second = ingest_file(store, path)

    assert second.replaced
    assert len(rows(store, "SELECT id FROM documents")) == 1
    assert len(rows(store, "SELECT id FROM attendees")) == 3
    assert len(rows(store, "SELECT id FROM chunks")) == second.chunks


def test_a_replaced_document_leaves_nothing_behind_in_the_index(
    store, write_transcript, make_meeting
):
    path = write_transcript()
    ingest_file(store, path)

    edited = make_meeting(
        turns=[{"speaker": "Priya", "text": "The oscilloscope needs recalibrating."}],
        action_items=[],
    )
    path.write_text(render_meeting(edited), encoding="utf-8")
    ingest_file(store, path)

    assert not rows(
        store, "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'connectors'"
    )
    assert rows(
        store, "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'oscilloscope'"
    )


def test_two_transcripts_are_two_documents(store, write_transcript):
    done, failures = ingest_paths(
        store,
        [write_transcript("first"), write_transcript("second", subject="Tooling sync")],
    )
    assert not failures
    assert {result.slug for result in done} == {"first", "second"}
    assert len(rows(store, "SELECT id FROM documents")) == 2


def test_a_file_that_is_not_a_transcript_is_reported_not_raised(
    store, tmp_path, write_transcript
):
    broken = tmp_path / "notes.md"
    broken.write_text("Just some notes.\n", encoding="utf-8")

    done, failures = ingest_paths(store, [broken, write_transcript()])

    assert len(done) == 1
    assert len(failures) == 1
    assert "notes.md" in str(failures[0])
    assert len(rows(store, "SELECT id FROM documents")) == 1


def test_a_bad_transcript_writes_nothing_at_all(store, tmp_path):
    broken = tmp_path / "notes.md"
    broken.write_text("Just some notes.\n", encoding="utf-8")
    with pytest.raises(IngestError):
        ingest_file(store, broken)
    assert not rows(store, "SELECT id FROM documents")


def test_a_failure_partway_through_leaves_the_store_as_it_was(
    store, write_transcript, monkeypatch
):
    path = write_transcript()
    first = ingest_file(store, path)
    before = rows(store, "SELECT id, ordinal, text FROM chunks ORDER BY ordinal")

    def bad_chunks(turns, target_words=250):
        """Return chunks that collide on ordinal, so the second insert fails."""
        return [
            Chunk(
                ordinal=0,
                text=text,
                word_count=1,
                kind=TURN_WINDOW,
                location="turn 0",
                span_start=0,
                span_end=0,
            )
            for text in ("one", "two")
        ]

    monkeypatch.setattr(transcripts, "chunk_turns", bad_chunks)
    with pytest.raises(sqlite3.IntegrityError):
        ingest_file(store, path)

    documents = rows(store, "SELECT id, slug FROM documents")
    assert len(documents) == 1
    assert documents[0]["id"] == first.document_id
    assert (
        rows(store, "SELECT id, ordinal, text FROM chunks ORDER BY ordinal") == before
    )
    assert len(rows(store, "SELECT id FROM attendees")) == 3


def test_document_paths_lists_readable_files_in_name_order(tmp_path, write_transcript):
    write_transcript("beta")
    write_transcript("alpha")
    (tmp_path / "alpha.json").write_text("{}", encoding="utf-8")
    assert [path.name for path in document_paths(tmp_path)] == [
        "alpha.md",
        "beta.md",
    ]


def test_document_paths_on_a_missing_directory_is_empty(tmp_path):
    assert document_paths(tmp_path / "absent") == []


def test_ingesting_the_same_file_twice_gives_the_same_chunk_text(
    store, write_transcript
):
    path = write_transcript()
    ingest_file(store, path)
    first = [
        row["text"] for row in rows(store, "SELECT text FROM chunks ORDER BY ordinal")
    ]
    ingest_file(store, path)
    second = [
        row["text"] for row in rows(store, "SELECT text FROM chunks ORDER BY ordinal")
    ]
    assert first == second
