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
    KINDS,
    SCHEMA_VERSION,
    SCHEMA_VERSION_KEY,
    CaptureSchemaVersionError,
    UnknownAnswerError,
    UnknownRecordError,
    connect,
    corrections,
    feedback,
    gaps,
    mark_reviewed,
    record,
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


def test_a_record_carries_the_citations_of_its_answer(records) -> None:
    """Opening a record shows what the answer rested on, without a second read."""
    answer_id = an_answer(records, citations=[A_CITATION])

    record_gap(records, answer_id)
    record_correction(records, answer_id, what_was_wrong="x", what_is_right="y")
    record_feedback(records, answer_id, verdict="down")

    for row in (gaps(records)[0], corrections(records)[0], feedback(records)[0]):
        assert row["citations"] == [A_CITATION]


def test_a_new_record_has_not_been_reviewed(records) -> None:
    """Everything starts in the queue as new."""
    answer_id = an_answer(records)

    written = record_feedback(records, answer_id, verdict="down")

    assert written["reviewed_at"] is None


@pytest.mark.parametrize("kind", KINDS)
def test_one_record_can_be_read_by_its_id(records, kind) -> None:
    """A single record comes back exactly as the list of its kind has it."""
    answer_id = an_answer(records)
    record_gap(records, answer_id)
    record_correction(records, answer_id, what_was_wrong="x", what_is_right="y")
    record_feedback(records, answer_id, verdict="up")
    readers = {"gaps": gaps, "corrections": corrections, "feedback": feedback}
    [listed] = readers[kind](records)

    assert record(records, kind, listed["id"]) == listed


@pytest.mark.parametrize("kind", KINDS)
def test_reading_an_id_that_is_not_there_is_refused(records, kind) -> None:
    """An unknown id is reported rather than answered with nothing."""
    with pytest.raises(UnknownRecordError):
        record(records, kind, 404)


def test_a_kind_that_is_not_one_of_the_three_is_refused(records) -> None:
    """The kind names a table, so anything else stops before any SQL runs."""
    with pytest.raises(ValueError):
        record(records, "answers", 1)
    with pytest.raises(ValueError):
        mark_reviewed(records, "answers; DROP TABLE gaps", 1)


def test_marking_a_record_reviewed_persists(tmp_path) -> None:
    """The mark survives the connection, so a reader sees it next time too."""
    path = tmp_path / "usage.db"
    first = connect(path)
    try:
        answer_id = an_answer(first)
        written = record_correction(
            first, answer_id, what_was_wrong="x", what_is_right="y"
        )
        marked = mark_reviewed(first, "corrections", written["id"])
    finally:
        first.close()

    second = connect(path)
    try:
        [row] = corrections(second)
    finally:
        second.close()

    assert marked["reviewed_at"]
    assert row["reviewed_at"] == marked["reviewed_at"]
    assert row | {"reviewed_at": None} == written


def test_marking_twice_keeps_the_first_time(records) -> None:
    """Repeating the request does not move when the item was first seen."""
    answer_id = an_answer(records)
    written = record_gap(records, answer_id)
    first = mark_reviewed(records, "gaps", written["id"])
    records.execute(
        "UPDATE gaps SET reviewed_at = '2026-01-01T00:00:00.000Z' WHERE id = ?",
        (written["id"],),
    )
    records.commit()

    again = mark_reviewed(records, "gaps", written["id"])

    assert first["reviewed_at"]
    assert again["reviewed_at"] == "2026-01-01T00:00:00.000Z"


def test_a_review_mark_can_be_cleared(records) -> None:
    """A mistaken click puts the item back among the new ones."""
    answer_id = an_answer(records)
    written = record_feedback(records, answer_id, verdict="down")
    mark_reviewed(records, "feedback", written["id"])

    cleared = mark_reviewed(records, "feedback", written["id"], reviewed=False)

    assert cleared["reviewed_at"] is None
    assert feedback(records)[0]["reviewed_at"] is None


def test_marking_only_touches_the_record_named(records) -> None:
    """Gap 1 and correction 1 are different records despite sharing an id."""
    answer_id = an_answer(records)
    gap = record_gap(records, answer_id)
    correction = record_correction(
        records, answer_id, what_was_wrong="x", what_is_right="y"
    )
    assert gap["id"] == correction["id"]

    mark_reviewed(records, "gaps", gap["id"])

    assert gaps(records)[0]["reviewed_at"]
    assert corrections(records)[0]["reviewed_at"] is None


def test_marking_an_id_that_is_not_there_is_refused(records) -> None:
    """Nothing is written, and the caller hears that nothing matched."""
    with pytest.raises(UnknownRecordError):
        mark_reviewed(records, "corrections", 404)


def test_a_file_from_before_reviewing_is_brought_up_to_date(tmp_path) -> None:
    """Rows written before the review mark existed are kept, and read as new.

    The version-1 file is made by taking the column back off a current one,
    which leaves exactly the tables that version wrote.
    """
    path = tmp_path / "usage.db"
    old = connect(path)
    try:
        answer_id = an_answer(old)
        record_gap(old, answer_id, routing=A_ROUTING)
        record_correction(old, answer_id, what_was_wrong="x", what_is_right="y")
        record_feedback(old, answer_id, verdict="down", note="stale")
        for table in KINDS:
            old.execute(f"ALTER TABLE {table} DROP COLUMN reviewed_at")
        old.execute(
            "UPDATE capture_meta SET value = '1' WHERE key = ?", (SCHEMA_VERSION_KEY,)
        )
        old.commit()
    finally:
        old.close()

    upgraded = connect(path)
    try:
        (version,) = upgraded.execute(
            "SELECT value FROM capture_meta WHERE key = ?", (SCHEMA_VERSION_KEY,)
        ).fetchone()
        rows = [gaps(upgraded)[0], corrections(upgraded)[0], feedback(upgraded)[0]]
        marked = mark_reviewed(upgraded, "feedback", rows[2]["id"])
    finally:
        upgraded.close()

    assert int(version) == SCHEMA_VERSION
    assert rows[0]["routing"] == A_ROUTING
    assert rows[2]["note"] == "stale"
    assert all(row["reviewed_at"] is None for row in rows)
    assert marked["reviewed_at"]
