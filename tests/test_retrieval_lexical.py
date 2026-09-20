"""Tests for BM25 search over chunks_fts."""

from __future__ import annotations

import sqlite3

import pytest

from corpus_query.retrieval.lexical import search_lexical, terms, unmatched_terms
from corpus_query.store.db import connect


def _insert_document(connection: sqlite3.Connection, slug: str = "meeting-1") -> int:
    cursor = connection.execute(
        """
        INSERT INTO documents (slug, source_path, subject, meeting_date)
        VALUES (?, ?, ?, ?)
        """,
        (slug, f"transcripts/{slug}.md", "Weekly sync", "2026-01-05"),
    )
    connection.commit()
    return cursor.lastrowid


def _insert_chunk(
    connection: sqlite3.Connection, document_id: int, ordinal: int, text: str
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, word_count, turn_start, turn_end, kind)
        VALUES (?, ?, ?, ?, 0, 0, 'turn_window')
        """,
        (document_id, ordinal, text, len(text.split())),
    )
    connection.commit()
    return cursor.lastrowid


@pytest.fixture
def connection() -> sqlite3.Connection:
    return connect(":memory:")


def test_finds_chunks_containing_a_query_term(connection):
    document_id = _insert_document(connection)
    matching_id = _insert_chunk(
        connection, document_id, 0, "The connector lead time slipped two weeks."
    )
    _insert_chunk(connection, document_id, 1, "Firmware review went fine.")

    hits = search_lexical(connection, "connector lead time")

    assert [hit.chunk_id for hit in hits] == [matching_id]


def test_ranks_a_chunk_matching_more_terms_higher(connection):
    document_id = _insert_document(connection)
    two_terms = _insert_chunk(
        connection, document_id, 0, "connector lead time connector lead time"
    )
    one_term = _insert_chunk(connection, document_id, 1, "connector arrived today")

    hits = search_lexical(connection, "connector lead time")

    assert [hit.chunk_id for hit in hits] == [two_terms, one_term]


def test_scores_are_higher_is_better(connection):
    document_id = _insert_document(connection)
    _insert_chunk(connection, document_id, 0, "connector lead time update today")
    _insert_chunk(connection, document_id, 1, "connector mentioned once")

    hits = search_lexical(connection, "connector lead time")

    assert hits[0].score >= hits[1].score


def test_empty_result_is_not_an_error(connection):
    _insert_document(connection)

    hits = search_lexical(connection, "nothing in this empty corpus")

    assert hits == []


def test_limit_bounds_the_number_of_hits(connection):
    document_id = _insert_document(connection)
    for ordinal in range(5):
        _insert_chunk(connection, document_id, ordinal, "connector lead time")

    hits = search_lexical(connection, "connector", limit=2)

    assert len(hits) == 2


@pytest.mark.parametrize(
    "query",
    [
        'a "quoted" phrase',
        "wildcard* search",
        "boosted^2 term",
        "supply OR chain",
        'bare "OR" * ^ mix',
    ],
)
def test_fts5_special_characters_do_not_error_or_change_meaning(connection, query):
    document_id = _insert_document(connection)
    _insert_chunk(connection, document_id, 0, "Nothing here matches that query.")

    # Must not raise sqlite3.OperationalError from malformed FTS5 syntax,
    # and must not silently become a boolean OR/NOT query over unrelated
    # terms that happens to match everything.
    hits = search_lexical(connection, query)

    assert hits == []


def test_a_literal_or_token_is_treated_as_a_search_term_not_an_operator(connection):
    document_id = _insert_document(connection)
    literal_or = _insert_chunk(connection, document_id, 0, "Option OR fallback plan")
    unrelated = _insert_chunk(connection, document_id, 1, "Completely unrelated text")

    hits = search_lexical(connection, "OR")

    ids = [hit.chunk_id for hit in hits]
    assert literal_or in ids
    assert unrelated not in ids


def test_terms_lowercases_and_drops_punctuation():
    assert terms('Connector "lead"-time OR *boost*') == [
        "connector",
        "lead",
        "time",
        "or",
        "boost",
    ]


def test_unmatched_terms_reports_terms_with_no_hits(connection):
    document_id = _insert_document(connection)
    _insert_chunk(connection, document_id, 0, "connector lead time update")

    missing = unmatched_terms(connection, "connector zyzzyva")

    assert missing == ["zyzzyva"]


def test_unmatched_terms_is_empty_when_everything_matches(connection):
    document_id = _insert_document(connection)
    _insert_chunk(connection, document_id, 0, "connector lead time update")

    missing = unmatched_terms(connection, "connector lead")

    assert missing == []
