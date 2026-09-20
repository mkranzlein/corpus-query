"""Tests for the hybrid retrieval pipeline.

Ranking is arithmetic over rankings, so no model loads here: the embedder
and the reranker are both stubbed with fixed vectors and canned scores.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from corpus_query.retrieval import index as index_module
from corpus_query.retrieval.blobs import vector_to_blob
from corpus_query.retrieval.search import search
from corpus_query.store.kinds import DOCX, TRANSCRIPT


def _insert_document(
    connection: sqlite3.Connection,
    slug: str,
    title: str = "Weekly sync",
    document_date: str = "2026-01-05",
    source_kind: str = TRANSCRIPT,
    author: str | None = None,
    time_sensitivity: str | None = "near_term",
    business_impact: str | None = "moderate",
    topics: list[str] = (),
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO documents
            (slug, source_path, source_kind, title, document_date, author,
             time_sensitivity, business_impact)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            f"transcripts/{slug}.md",
            source_kind,
            title,
            document_date,
            author,
            time_sensitivity,
            business_impact,
        ),
    )
    document_id = cursor.lastrowid
    for name in topics:
        (topic_id,) = connection.execute(
            "INSERT INTO topics (name) VALUES (?) RETURNING id", (name,)
        ).fetchone()
        connection.execute(
            "INSERT INTO document_topics (document_id, topic_id) VALUES (?, ?)",
            (document_id, topic_id),
        )
    connection.commit()
    return document_id


def _insert_chunk(
    connection: sqlite3.Connection,
    document_id: int,
    ordinal: int,
    text: str,
    embedding: np.ndarray,
    span_start: int = 0,
    span_end: int = 0,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, word_count, location,
             span_start, span_end, kind,
             embedding, embedding_model, embedding_dim)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'turn_window', ?, 'test-model', ?)
        """,
        (
            document_id,
            ordinal,
            text,
            len(text.split()),
            f"turns {span_start}-{span_end}",
            span_start,
            span_end,
            vector_to_blob(embedding),
            len(embedding),
        ),
    )
    connection.commit()
    return cursor.lastrowid


@pytest.fixture
def connection() -> sqlite3.Connection:
    from corpus_query.store.db import connect

    return connect(":memory:")


def _vector(axis: int) -> np.ndarray:
    vector = np.zeros(3, dtype=np.float32)
    vector[axis] = 1.0
    return vector


def _fake_embed(vector: np.ndarray):
    def embed(texts):
        return np.array([vector for _ in texts], dtype=np.float32)

    return embed


def _score_by_shared_words(query: str, documents):
    query_words = set(query.lower().split())
    return [
        float(len(query_words & set(document.lower().split())))
        for document in documents
    ]


def test_returns_full_metadata_for_each_result(connection, tmp_path):
    document_id = _insert_document(
        connection,
        "meeting-1",
        title="Rev B schedule",
        document_date="2026-03-04",
        time_sensitivity="urgent",
        business_impact="critical",
        topics=["Firmware", "Supply chain"],
    )
    chunk_id = _insert_chunk(
        connection,
        document_id,
        0,
        "The connector lead time slipped two weeks.",
        _vector(0),
        span_start=2,
        span_end=4,
    )
    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = search(
        connection,
        collection,
        "connector lead time",
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    [only] = result.results
    assert only.chunk_id == chunk_id
    assert only.text == "The connector lead time slipped two weeks."
    assert only.document_slug == "meeting-1"
    assert only.source_kind == TRANSCRIPT
    assert only.title == "Rev B schedule"
    assert only.document_date == "2026-03-04"
    assert only.author is None
    assert only.location == "turns 2-4"
    assert only.span_start == 2
    assert only.span_end == 4
    assert set(only.topics) == {"Firmware", "Supply chain"}
    assert only.time_sensitivity == "urgent"
    assert only.business_impact == "critical"
    assert only.rank == 1
    assert only.rerank_score == pytest.approx(3.0)


def test_a_single_author_document_reports_its_kind_and_author(connection, tmp_path):
    document_id = _insert_document(
        connection,
        "thermal-review",
        title="Thermal review",
        source_kind=DOCX,
        author="Devon",
    )
    _insert_chunk(
        connection,
        document_id,
        0,
        "The connector lead time slipped two weeks.",
        _vector(0),
    )
    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = search(
        connection,
        collection,
        "connector lead time",
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    [only] = result.results
    assert only.source_kind == DOCX
    assert only.author == "Devon"
    assert only.title == "Thermal review"


def test_result_count_defaults_to_five_and_is_a_parameter(connection, tmp_path):
    document_id = _insert_document(connection, "meeting-1")
    for ordinal in range(8):
        _insert_chunk(
            connection,
            document_id,
            ordinal,
            f"connector lead time chunk {ordinal}",
            _vector(ordinal % 3),
        )
    collection = index_module.build_index(connection, tmp_path / "chroma")

    default_result = search(
        connection,
        collection,
        "connector lead time",
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )
    small_result = search(
        connection,
        collection,
        "connector lead time",
        results=2,
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    assert len(default_result.results) == 5
    assert len(small_result.results) == 2


def test_a_chunk_found_by_only_dense_search_still_surfaces(connection, tmp_path):
    document_id = _insert_document(connection, "meeting-1")
    dense_only = _insert_chunk(
        connection, document_id, 0, "supplier delays discussion", _vector(0)
    )
    _insert_chunk(connection, document_id, 1, "unrelated firmware notes", _vector(1))
    collection = index_module.build_index(connection, tmp_path / "chroma")

    def rerank_favor_dense_only(query, documents):
        return [10.0 if "supplier" in doc else 0.0 for doc in documents]

    result = search(
        connection,
        collection,
        "parts arriving late",
        embed=_fake_embed(_vector(0)),
        rerank=rerank_favor_dense_only,
    )

    assert result.results[0].chunk_id == dense_only


def test_confidence_reports_top_score_and_margin(connection, tmp_path):
    document_id = _insert_document(connection, "meeting-1")
    _insert_chunk(connection, document_id, 0, "connector lead time alpha", _vector(0))
    _insert_chunk(connection, document_id, 1, "connector lead time beta", _vector(0))
    collection = index_module.build_index(connection, tmp_path / "chroma")

    def rerank(query, documents):
        return [10.0, 4.0]

    result = search(
        connection,
        collection,
        "connector lead time",
        embed=_fake_embed(_vector(0)),
        rerank=rerank,
    )

    assert result.confidence.top_score == pytest.approx(10.0)
    assert result.confidence.margin == pytest.approx(6.0)


def test_confidence_margin_is_none_with_a_single_result(connection, tmp_path):
    document_id = _insert_document(connection, "meeting-1")
    _insert_chunk(connection, document_id, 0, "connector lead time", _vector(0))
    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = search(
        connection,
        collection,
        "connector lead time",
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    assert result.confidence.margin is None


def test_confidence_reports_lexical_dense_agreement(connection, tmp_path):
    document_id = _insert_document(connection, "meeting-1")
    agreed = _insert_chunk(
        connection, document_id, 0, "connector lead time update", _vector(0)
    )
    _insert_chunk(connection, document_id, 1, "unrelated notes entirely", _vector(1))
    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = search(
        connection,
        collection,
        "connector lead time",
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    assert result.confidence.lexical_dense_agree is True
    assert result.results[0].chunk_id == agreed


def test_confidence_reports_disagreement_when_tops_differ(connection, tmp_path):
    document_id = _insert_document(connection, "meeting-1")
    # Lexical top: contains all query words. Dense top: closest vector.
    _insert_chunk(connection, document_id, 0, "connector lead time update", _vector(1))
    _insert_chunk(
        connection, document_id, 1, "totally unrelated content here", _vector(0)
    )
    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = search(
        connection,
        collection,
        "connector lead time",
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    assert result.confidence.lexical_dense_agree is False


def test_confidence_reports_unmatched_query_terms(connection, tmp_path):
    document_id = _insert_document(connection, "meeting-1")
    _insert_chunk(connection, document_id, 0, "connector lead time", _vector(0))
    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = search(
        connection,
        collection,
        "connector zyzzyva",
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    assert result.confidence.unmatched_terms == ["zyzzyva"]


def test_empty_corpus_returns_no_results_and_no_error(connection, tmp_path):
    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = search(
        connection,
        collection,
        "anything at all",
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    assert result.results == []
    assert result.confidence.top_score is None
    assert result.confidence.margin is None
    assert result.confidence.lexical_dense_agree is False


def test_candidates_is_a_parameter_that_bounds_the_fused_pool(connection, tmp_path):
    document_id = _insert_document(connection, "meeting-1")
    for ordinal in range(10):
        _insert_chunk(
            connection,
            document_id,
            ordinal,
            f"connector lead time chunk {ordinal}",
            _vector(ordinal % 3),
        )
    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = search(
        connection,
        collection,
        "connector lead time",
        candidates=3,
        results=10,
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    # candidates=3 caps each half's contribution; fused pool can be larger
    # than 3 when the two halves disagree, but bounded well under all 10.
    assert len(result.results) <= 6


def test_results_equal_to_zero_returns_no_results(connection, tmp_path):
    document_id = _insert_document(connection, "meeting-1")
    _insert_chunk(connection, document_id, 0, "connector lead time", _vector(0))
    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = search(
        connection,
        collection,
        "connector lead time",
        results=0,
        embed=_fake_embed(_vector(0)),
        rerank=_score_by_shared_words,
    )

    assert result.results == []


def test_the_default_embed_and_rerank_are_the_projects(
    connection, tmp_path, monkeypatch
):
    """Cover the default wiring without installing torch.

    :mod:`corpus_query.retrieval.search` imports both lazily through
    :mod:`corpus_query.retrieval.dense` and its own ``_project_rerank``, so
    stand-in modules in ``sys.modules`` prove the wiring without needing the
    real models loaded.
    """
    import sys
    import types

    document_id = _insert_document(connection, "meeting-1")
    _insert_chunk(connection, document_id, 0, "connector lead time", _vector(0))
    collection = index_module.build_index(connection, tmp_path / "chroma")

    embedder_module = types.ModuleType("corpus_query.models.embedder")
    embedder_module.embed_queries = lambda texts: np.array(
        [_vector(0) for _ in texts], dtype=np.float32
    )
    reranker_module = types.ModuleType("corpus_query.models.reranker")
    reranker_module.score = lambda query, documents: [1.0 for _ in documents]
    monkeypatch.setitem(sys.modules, "corpus_query.models.embedder", embedder_module)
    monkeypatch.setitem(sys.modules, "corpus_query.models.reranker", reranker_module)

    result = search(connection, collection, "connector lead time")

    assert len(result.results) == 1
    assert result.results[0].rerank_score == pytest.approx(1.0)
