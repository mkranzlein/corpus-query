"""Tests for the SQL that reads answer quality over time.

The queries are the ones ``docs/answer-metrics.md`` prints, read out of the
file rather than copied here, so the note cannot drift from the schema
without this failing. Each runs against a usage database holding a few
answers whose rates are known in advance.

Nothing here calls a model.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from corpus_query.store import capture, spans
from corpus_query.store.spans import SpanRow

NOTE = Path(__file__).resolve().parents[1] / "docs" / "answer-metrics.md"

#: A trace id for the one answer that has spans.
TRACE = "0af7651916cd43dd8448eb211c80319c"


def queries() -> dict[str, str]:
    """Read the note's SQL blocks, keyed by the comment each one opens with.

    Returns:
        Each query, keyed by its first line without the ``--``.
    """
    blocks = re.findall(r"```sql\n(.*?)```", NOTE.read_text(encoding="utf-8"), re.S)
    return {block.splitlines()[0].removeprefix("--").strip(): block for block in blocks}


def answer(
    connection: sqlite3.Connection,
    day: str,
    *,
    searches: int | None,
    abstained: bool = False,
    coverage: float | None = None,
    corrections: int = 0,
    trace_id: str | None = None,
) -> str:
    """Write one answer as though it were given on a particular day.

    Args:
        connection: An open capture connection.
        day: The date it was given, as ``YYYY-MM-DD``.
        searches: How many searches it ran, or None for a row from before
            the count was recorded.
        abstained: Whether it abstained.
        coverage: Its citation coverage.
        corrections: How many corrections to write against it.
        trace_id: The trace it was produced under.

    Returns:
        Its id.
    """
    answer_id = capture.record_answer(
        connection,
        query="q",
        answer="a",
        citations=[],
        thread_id="thread-1",
        abstained=abstained,
        searches=searches,
        citation_coverage=coverage,
        trace_id=trace_id,
    )
    with connection:
        connection.execute(
            "UPDATE answers SET created_at = ? WHERE id = ?",
            (f"{day}T12:00:00.000Z", answer_id),
        )
    for _ in range(corrections):
        capture.record_correction(connection, answer_id, "wrong", "right")
    return answer_id


@pytest.fixture
def usage(tmp_path):
    """Return a usage database holding two days of answers.

    On the first day, of the turns that searched, one answered and was
    corrected and one abstained. A decline that searched nothing and a row
    from before searches were counted are there too, and fall out of every
    rate. On the second day both turns that searched answered, at coverage
    0.5 and 0.0, and one was corrected twice, which still counts once.
    """
    path = tmp_path / "usage.db"
    spans.connect(path).close()
    connection = capture.connect(path)
    answer(connection, "2026-09-01", searches=1, coverage=1.0, corrections=1)
    answer(connection, "2026-09-01", searches=1, abstained=True, trace_id=TRACE)
    answer(connection, "2026-09-01", searches=0)
    answer(connection, "2026-09-01", searches=None, abstained=True, corrections=1)
    answer(connection, "2026-09-02", searches=2, coverage=0.5)
    answer(connection, "2026-09-02", searches=1, coverage=0.0, corrections=2)
    try:
        yield connection
    finally:
        connection.close()


def rows(connection: sqlite3.Connection, sql: str) -> list[tuple]:
    """Run one query and return its rows as plain tuples."""
    return [tuple(row) for row in connection.execute(sql)]


def test_the_note_prints_each_query() -> None:
    """The three rates, and the way from a number back to its spans."""
    assert set(queries()) == {
        "abstention rate by day",
        "citation coverage by day",
        "correction rate by day",
        "the spans behind the least supported answers",
    }


def test_abstention_rate_by_day(usage) -> None:
    """Abstentions over the turns that consulted the record."""
    assert rows(usage, queries()["abstention rate by day"]) == [
        ("2026-09-01", 2, 0.5),
        ("2026-09-02", 2, 0.0),
    ]


def test_citation_coverage_by_day(usage) -> None:
    """Mean coverage over the answers that did not abstain."""
    assert rows(usage, queries()["citation coverage by day"]) == [
        ("2026-09-01", 1, 1.0),
        ("2026-09-02", 2, 0.25),
    ]


def test_correction_rate_by_day(usage) -> None:
    """Answers corrected at least once, over the turns that searched."""
    assert rows(usage, queries()["correction rate by day"]) == [
        ("2026-09-01", 2, 0.5),
        ("2026-09-02", 2, 0.5),
    ]


def test_a_row_leads_to_its_spans(usage) -> None:
    """The trace id is the whole of the join from a number to an execution."""
    usage.execute(
        "UPDATE answers SET citation_coverage = 0.0 WHERE trace_id = ?", (TRACE,)
    )
    usage.commit()
    spans.write(
        usage,
        [
            SpanRow(
                trace_id=TRACE,
                span_id="00f067aa0ba902b7",
                parent_span_id=None,
                name="invoke_agent corpus-query",
                kind="INTERNAL",
                start_time_unix_nano=1_000_000_000,
                end_time_unix_nano=1_250_000_000,
                status_code="UNSET",
                status_message=None,
                attributes={},
                events=[],
                scope="corpus_query",
            )
        ],
    )

    assert rows(usage, queries()["the spans behind the least supported answers"]) == [
        ("q", 0.0, "invoke_agent corpus-query", 250.0)
    ]
