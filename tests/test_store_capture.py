"""Tests for the captured record of gaps, corrections, and feedback.

Everything here runs against a real SQLite file under ``tmp_path``, because
what is worth asserting is mostly about the file: that the tables are created
on demand, that a record cannot point at an answer that is not there, and
that a read comes back with enough on it to be read without a second call.
Nothing here calls a model.
"""

from __future__ import annotations

import sqlite3

import pytest

from corpus_query.store.capture import (
    SCHEMA_VERSION,
    SCHEMA_VERSION_KEY,
    CaptureSchemaVersionError,
    UnknownAnswerError,
    connect,
    corrections,
    feedback,
    gaps,
    record_answer,
    record_correction,
    record_feedback,
    record_gap,
)

A_CITATION = {
    "chunk_id": 7,
    "document_slug": "rev-b-schedule",
    "source_kind": "transcript",
    "title": "Rev B schedule",
    "document_date": "2026-03-04",
    "author": None,
    "attendees": ["Priya", "Marcus"],
    "location": "turns 0-1",
}

A_ROUTING = {
    "candidates": [
        {
            "name": "Sofia",
            "role": "Firmware Engineer",
            "department": "Engineering",
            "passages": 1,
            "evidence": [A_CITATION],
        }
    ],
    "question": "Which Rev B units are installed in hot environments?",
}


@pytest.fixture
def records(tmp_path):
    """Return an open capture store in a temporary usage database."""
    connection = connect(tmp_path / "usage.db")
    try:
        yield connection
    finally:
        connection.close()


def an_answer(
    connection: sqlite3.Connection,
    query: str = "Where are the rev B boards?",
    answer: str = "Marcus put them two weeks out.",
    citations: list | None = None,
    thread_id: str = "thread-1",
    abstained: bool = False,
) -> str:
    """Write one answer row and return its id."""
    return record_answer(
        connection,
        query=query,
        answer=answer,
        citations=[A_CITATION] if citations is None else citations,
        thread_id=thread_id,
        abstained=abstained,
    )


def test_the_tables_are_created_on_demand(tmp_path) -> None:
    """A fresh clone needs no setup step before a question can be recorded."""
    path = tmp_path / "nested" / "usage.db"

    connection = connect(path)
    try:
        assert path.exists()
        assert an_answer(connection)
    finally:
        connection.close()


def test_the_version_is_recorded_beside_the_tables_not_on_the_file(records) -> None:
    """The file's user_version is left alone; the tables carry their own.

    The usage database is shared with the graph checkpointer, which creates
    its own tables here and does not version the file. Claiming that pragma
    would be speaking for tables this project does not own.
    """
    (stored,) = records.execute(
        "SELECT value FROM capture_meta WHERE key = ?", (SCHEMA_VERSION_KEY,)
    ).fetchone()
    (pragma,) = records.execute("PRAGMA user_version").fetchone()

    assert int(stored) == SCHEMA_VERSION
    assert pragma == 0


def test_opening_a_file_twice_keeps_what_is_in_it(tmp_path) -> None:
    """Restarting the service does not recreate or clear the tables."""
    first = connect(tmp_path / "usage.db")
    try:
        answer_id = an_answer(first)
        record_feedback(first, answer_id, verdict="up")
    finally:
        first.close()

    second = connect(tmp_path / "usage.db")
    try:
        assert len(feedback(second)) == 1
    finally:
        second.close()


def test_a_newer_schema_is_refused_rather_than_written_to(tmp_path) -> None:
    """A file written by later code is reported, not silently appended to."""
    connection = connect(tmp_path / "usage.db")
    try:
        connection.execute(
            "UPDATE capture_meta SET value = ? WHERE key = ?",
            (str(SCHEMA_VERSION + 1), SCHEMA_VERSION_KEY),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(CaptureSchemaVersionError) as caught:
        connect(tmp_path / "usage.db")

    assert str(SCHEMA_VERSION + 1) in str(caught.value)


def test_tables_another_writer_owns_are_left_alone(tmp_path) -> None:
    """The checkpointer's tables in the same file are neither read nor touched."""
    path = tmp_path / "usage.db"
    other = sqlite3.connect(path)
    try:
        other.execute("CREATE TABLE checkpoints (thread_id TEXT)")
        other.execute("INSERT INTO checkpoints VALUES ('thread-1')")
        other.commit()
    finally:
        other.close()

    connection = connect(path)
    try:
        assert an_answer(connection)
        (kept,) = connection.execute("SELECT count(*) FROM checkpoints").fetchone()
    finally:
        connection.close()

    assert kept == 1


def test_an_answer_row_comes_back_on_every_record(records) -> None:
    """Each kind of record carries the question and answer it hangs off."""
    answer_id = an_answer(records, query="Where are the boards?")

    record_gap(records, answer_id)
    record_correction(
        records, answer_id, what_was_wrong="the date", what_is_right="March 19th"
    )
    record_feedback(records, answer_id, verdict="down", note="not what I asked")

    for row in (gaps(records)[0], corrections(records)[0], feedback(records)[0]):
        assert row["answer_id"] == answer_id
        assert row["question"] == "Where are the boards?"
        assert row["answer"] == "Marcus put them two weeks out."
        assert row["thread_id"] == "thread-1"
        assert row["abstained"] is False
        assert row["created_at"]


def test_a_gap_carries_the_routing_that_was_suggested(records) -> None:
    """The suggestion made at the time is stored with the gap, not rebuilt."""
    answer_id = an_answer(records, answer="The record does not say.", abstained=True)

    record_gap(records, answer_id, routing=A_ROUTING)

    [row] = gaps(records)
    assert row["routing"] == A_ROUTING
    assert row["abstained"] is True


def test_a_gap_without_a_suggestion_is_still_a_gap(records) -> None:
    """Nothing came back and nobody was named, and the gap is recorded anyway."""
    answer_id = an_answer(records, abstained=True)

    record_gap(records, answer_id)

    [row] = gaps(records)
    assert row["routing"] is None


def test_a_correction_says_what_was_wrong_and_what_is_right(records) -> None:
    """Both halves are recorded; one without the other is not a correction."""
    answer_id = an_answer(records)

    written = record_correction(
        records,
        answer_id,
        what_was_wrong="It said the freeze is March 12th.",
        what_is_right="The freeze moved to March 19th.",
    )

    assert written["what_was_wrong"] == "It said the freeze is March 12th."
    assert written["what_is_right"] == "The freeze moved to March 19th."
    assert corrections(records) == [written]


@pytest.mark.parametrize("verdict", ["up", "down"])
def test_feedback_records_either_verdict(records, verdict) -> None:
    """A verdict with no note is a complete record."""
    answer_id = an_answer(records)

    written = record_feedback(records, answer_id, verdict=verdict)

    assert written["verdict"] == verdict
    assert written["note"] is None


def test_feedback_keeps_the_note_when_there_is_one(records) -> None:
    """A note is the part a reader can act on, so it is stored as written."""
    answer_id = an_answer(records)

    written = record_feedback(
        records, answer_id, verdict="down", note="cited the wrong meeting"
    )

    assert written["note"] == "cited the wrong meeting"


def test_a_verdict_that_is_neither_up_nor_down_is_refused(records) -> None:
    """The two verdicts are the contract, at the store as well as the API."""
    answer_id = an_answer(records)

    with pytest.raises(ValueError):
        record_feedback(records, answer_id, verdict="sideways")

    assert feedback(records) == []


@pytest.mark.parametrize(
    "write",
    [
        pytest.param(lambda c, i: record_gap(c, i), id="gap"),
        pytest.param(
            lambda c, i: record_correction(c, i, what_was_wrong="x", what_is_right="y"),
            id="correction",
        ),
        pytest.param(lambda c, i: record_feedback(c, i, verdict="up"), id="feedback"),
    ],
)
def test_a_write_against_an_unknown_answer_is_refused(records, write) -> None:
    """An orphan is worse than a refusal: nothing could ever read it back."""
    an_answer(records)

    with pytest.raises(UnknownAnswerError) as caught:
        write(records, "no-such-answer")

    assert "no-such-answer" in str(caught.value)
    assert gaps(records) == corrections(records) == feedback(records) == []


def test_records_come_back_most_recent_first(records) -> None:
    """A reader catching up wants the newest first, not the oldest."""
    answer_id = an_answer(records)
    for note in ("first", "second", "third"):
        record_feedback(records, answer_id, verdict="down", note=note)

    assert [row["note"] for row in feedback(records)] == ["third", "second", "first"]


def test_a_read_stops_at_the_limit_it_was_given(records) -> None:
    """These reads are for catching up, not for exporting the table."""
    answer_id = an_answer(records)
    for note in ("first", "second", "third"):
        record_feedback(records, answer_id, verdict="up", note=note)

    rows = feedback(records, limit=2)

    assert [row["note"] for row in rows] == ["third", "second"]


def test_citations_survive_the_round_trip(records) -> None:
    """What the answer rested on is stored whole and comes back unchanged."""
    answer_id = an_answer(records, citations=[A_CITATION])

    record_gap(records, answer_id)
    (stored,) = records.execute(
        "SELECT citations FROM answers WHERE id = ?", (answer_id,)
    ).fetchone()

    assert A_CITATION["location"] in stored


def test_every_answer_gets_its_own_id(records) -> None:
    """The same question asked twice is two answers, each correctable."""
    first = an_answer(records)
    second = an_answer(records)

    assert first != second
