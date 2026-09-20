"""Tests for building and opening the Chroma vector index."""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from corpus_query.retrieval import index as index_module
from corpus_query.retrieval.blobs import vector_to_blob
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
    embedding: np.ndarray | None = None,
) -> int:
    if embedding is None:
        cursor = connection.execute(
            """
            INSERT INTO chunks
                (document_id, ordinal, text, word_count, location,
                 span_start, span_end, kind)
            VALUES (?, ?, 'some text', 2, 'turn 0', 0, 0, 'turn_window')
            """,
            (document_id, ordinal),
        )
    else:
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


def _vector(seed: float) -> np.ndarray:
    rng = np.random.default_rng(int(seed * 1000))
    return rng.random(8).astype(np.float32)


@pytest.fixture
def connection() -> sqlite3.Connection:
    return connect(":memory:")


def test_build_indexes_only_chunks_with_an_embedding(connection, tmp_path):
    document_id = _insert_document(connection)
    embedded_id = _insert_chunk(connection, document_id, 0, embedding=_vector(1))
    _insert_chunk(connection, document_id, 1, embedding=None)

    collection = index_module.build_index(connection, tmp_path / "chroma")

    assert collection.count() == 1
    assert collection.get(ids=[str(embedded_id)])["ids"] == [str(embedded_id)]


def test_vector_id_is_the_chunk_row_id(connection, tmp_path):
    document_id = _insert_document(connection)
    vector = _vector(2)
    chunk_id = _insert_chunk(connection, document_id, 0, embedding=vector)

    collection = index_module.build_index(connection, tmp_path / "chroma")

    result = collection.get(ids=[str(chunk_id)], include=["embeddings"])
    assert result["ids"] == [str(chunk_id)]
    assert np.allclose(np.array(result["embeddings"][0], dtype=np.float32), vector)


def test_rebuilding_is_idempotent(connection, tmp_path):
    document_id = _insert_document(connection)
    _insert_chunk(connection, document_id, 0, embedding=_vector(3))
    path = tmp_path / "chroma"

    first_count = index_module.build_index(connection, path).count()
    second_count = index_module.build_index(connection, path).count()

    assert first_count == second_count == 1


def test_rebuild_drops_vectors_for_chunks_that_no_longer_exist(connection, tmp_path):
    document_id = _insert_document(connection)
    stale_id = _insert_chunk(connection, document_id, 0, embedding=_vector(4))
    path = tmp_path / "chroma"
    index_module.build_index(connection, path)

    connection.execute("DELETE FROM chunks WHERE id = ?", (stale_id,))
    connection.commit()
    collection = index_module.build_index(connection, path)

    assert collection.count() == 0


def test_open_index_builds_when_missing(connection, tmp_path):
    document_id = _insert_document(connection)
    _insert_chunk(connection, document_id, 0, embedding=_vector(5))

    collection = index_module.open_index(connection, tmp_path / "chroma")

    assert collection.count() == 1


def test_open_index_reuses_an_up_to_date_index(connection, tmp_path):
    document_id = _insert_document(connection)
    _insert_chunk(connection, document_id, 0, embedding=_vector(6))
    path = tmp_path / "chroma"
    index_module.build_index(connection, path)

    collection = index_module.open_index(connection, path)

    assert collection.count() == 1


def test_open_index_rebuilds_when_vector_count_disagrees(connection, tmp_path):
    document_id = _insert_document(connection)
    _insert_chunk(connection, document_id, 0, embedding=_vector(7))
    path = tmp_path / "chroma"
    index_module.build_index(connection, path)

    # A second embedded chunk lands after the index was built, without a
    # rebuild in between: the index is now stale by count.
    _insert_chunk(connection, document_id, 1, embedding=_vector(8))

    collection = index_module.open_index(connection, path)

    assert collection.count() == 2


def test_build_with_no_embedded_chunks_leaves_an_empty_collection(connection, tmp_path):
    _insert_document(connection)

    collection = index_module.build_index(connection, tmp_path / "chroma")

    assert collection.count() == 0
