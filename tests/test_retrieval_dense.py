"""Tests for dense search over the vector index."""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from corpus_query.retrieval import index as index_module
from corpus_query.retrieval.blobs import vector_to_blob
from corpus_query.retrieval.dense import search_dense
from corpus_query.store.db import connect


def _insert_document(connection: sqlite3.Connection, slug: str = "meeting-1") -> int:
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
    ordinal: int,
    embedding: np.ndarray,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, word_count, location,
             span_start, span_end, kind,
             embedding, embedding_model, embedding_dim)
        VALUES (
            ?, ?, 'some text', 2, 'turn 0', 0, 0, 'turn_window',
            ?, 'test-model', ?
        )
        """,
        (document_id, ordinal, vector_to_blob(embedding), len(embedding)),
    )
    connection.commit()
    return cursor.lastrowid


@pytest.fixture
def connection() -> sqlite3.Connection:
    return connect(":memory:")


def _fake_embed(vector: np.ndarray):
    def embed(texts):
        return np.array([vector for _ in texts], dtype=np.float32)

    return embed


def test_returns_the_closest_chunk_first(connection, tmp_path):
    document_id = _insert_document(connection)
    close = _insert_chunk(
        connection, document_id, 0, np.array([1.0, 0.0, 0.0], dtype=np.float32)
    )
    far = _insert_chunk(
        connection, document_id, 1, np.array([0.0, 1.0, 0.0], dtype=np.float32)
    )
    collection = index_module.build_index(connection, tmp_path / "chroma")

    hits = search_dense(
        collection,
        "query",
        embed=_fake_embed(np.array([1.0, 0.0, 0.0], dtype=np.float32)),
    )

    assert [hit.chunk_id for hit in hits] == [close, far]


def test_scores_are_similarity_not_distance_so_higher_is_better(connection, tmp_path):
    document_id = _insert_document(connection)
    _insert_chunk(
        connection, document_id, 0, np.array([1.0, 0.0, 0.0], dtype=np.float32)
    )
    collection = index_module.build_index(connection, tmp_path / "chroma")

    [hit] = search_dense(
        collection,
        "query",
        embed=_fake_embed(np.array([1.0, 0.0, 0.0], dtype=np.float32)),
    )

    # An exact match has cosine distance 0, so similarity should be ~1.
    assert hit.score == pytest.approx(1.0, abs=1e-5)


def test_limit_bounds_the_number_of_hits(connection, tmp_path):
    document_id = _insert_document(connection)
    for ordinal in range(5):
        vector = np.zeros(3, dtype=np.float32)
        vector[ordinal % 3] = 1.0
        _insert_chunk(connection, document_id, ordinal, vector)
    collection = index_module.build_index(connection, tmp_path / "chroma")

    hits = search_dense(
        collection,
        "query",
        limit=2,
        embed=_fake_embed(np.array([1.0, 0.0, 0.0], dtype=np.float32)),
    )

    assert len(hits) == 2


def test_empty_index_returns_no_hits(connection, tmp_path):
    _insert_document(connection)
    collection = index_module.build_index(connection, tmp_path / "chroma")

    hits = search_dense(
        collection,
        "query",
        embed=_fake_embed(np.array([1.0, 0.0, 0.0], dtype=np.float32)),
    )

    assert hits == []


def test_embed_receives_the_bare_query_text(connection, tmp_path):
    document_id = _insert_document(connection)
    _insert_chunk(
        connection, document_id, 0, np.array([1.0, 0.0, 0.0], dtype=np.float32)
    )
    collection = index_module.build_index(connection, tmp_path / "chroma")
    seen = []

    def embed(texts):
        seen.extend(texts)
        return np.array([[1.0, 0.0, 0.0]], dtype=np.float32)

    search_dense(collection, "supplier delays", embed=embed)

    assert seen == ["supplier delays"]


def test_the_default_embed_is_the_projects_query_side_embedder(
    connection, tmp_path, monkeypatch
):
    """Cover the default path without installing torch.

    :mod:`corpus_query.retrieval.dense` imports the embedder lazily, so a
    stand-in module put in ``sys.modules`` proves it reaches for the
    query-side function without needing the real one loaded.
    """
    import sys
    import types

    document_id = _insert_document(connection)
    _insert_chunk(
        connection, document_id, 0, np.array([1.0, 0.0, 0.0], dtype=np.float32)
    )
    collection = index_module.build_index(connection, tmp_path / "chroma")

    module = types.ModuleType("corpus_query.models.embedder")
    module.embed_queries = lambda texts: np.array(
        [[1.0, 0.0, 0.0] for _ in texts], dtype=np.float32
    )
    module.EMBEDDING_MODEL_ID = "stand-in-embedder"
    monkeypatch.setitem(sys.modules, "corpus_query.models.embedder", module)

    hits = search_dense(collection, "supplier delays")

    assert len(hits) == 1
