"""Tests for filling ``chunks.embedding``.

No model is loaded here. The embedding function is supplied by the test, so
what is checked is the bookkeeping around it: one vector per chunk, the
provenance recorded beside it, and nothing recomputed that already exists.
"""

from __future__ import annotations

import numpy as np
import pytest

from corpus_query.enrich.documents import SUMMARY
from corpus_query.enrich.embed import embed_document
from corpus_query.retrieval.blobs import blob_to_vector


def rows(connection, document_id):
    """Return every chunk row for a document, in order."""
    return connection.execute(
        """
        SELECT id, text, kind, embedding, embedding_model, embedding_dim
        FROM chunks WHERE document_id = ? ORDER BY ordinal
        """,
        (document_id,),
    ).fetchall()


def add_summary_chunk(connection, document_id, text="A summary."):
    """Write a summary chunk the way enrichment does."""
    (highest,) = connection.execute(
        "SELECT max(ordinal) FROM chunks WHERE document_id = ?", (document_id,)
    ).fetchone()
    connection.execute(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, word_count, turn_start, turn_end, kind)
        VALUES (?, ?, ?, 2, NULL, NULL, ?)
        """,
        (document_id, highest + 1, text, SUMMARY),
    )


def test_every_chunk_gets_a_vector_and_its_provenance(store, ingest, fake_embedder):
    embed, model_id = fake_embedder
    document_id = ingest(store, "rev-b-schedule")

    result = embed_document(store, document_id, embed=embed, model_id=model_id)

    stored = rows(store, document_id)
    assert result.written == len(stored)
    assert result.model_id == model_id
    assert result.dimension == 3
    for row in stored:
        assert row["embedding_model"] == model_id
        assert row["embedding_dim"] == 3
        assert len(blob_to_vector(row["embedding"])) == 3


def test_the_summary_chunk_is_embedded_like_any_other(store, ingest, fake_embedder):
    embed, model_id = fake_embedder
    document_id = ingest(store, "rev-b-schedule")
    add_summary_chunk(store, document_id)

    embed_document(store, document_id, embed=embed, model_id=model_id)

    summary = [row for row in rows(store, document_id) if row["kind"] == SUMMARY]
    assert summary
    assert all(row["embedding"] is not None for row in summary)


def test_the_stored_vector_is_the_one_the_embedder_produced(
    store, ingest, fake_embedder
):
    embed, model_id = fake_embedder
    document_id = ingest(store, "rev-b-schedule")

    embed_document(store, document_id, embed=embed, model_id=model_id)

    stored = rows(store, document_id)
    expected = embed([row["text"] for row in stored])
    for row, vector in zip(stored, expected, strict=True):
        assert np.array_equal(blob_to_vector(row["embedding"]), vector)


def test_rerunning_does_not_recompute_an_embedding_that_exists(
    store, ingest, fake_embedder
):
    embed, model_id = fake_embedder
    document_id = ingest(store, "rev-b-schedule")
    embed_document(store, document_id, embed=embed, model_id=model_id)
    calls = []

    def counting(texts):
        calls.append(list(texts))
        return embed(texts)

    result = embed_document(store, document_id, embed=counting, model_id=model_id)

    assert calls == []
    assert result.written == 0
    assert result.skipped == len(rows(store, document_id))


def test_only_the_chunk_without_an_embedding_is_computed(store, ingest, fake_embedder):
    embed, model_id = fake_embedder
    document_id = ingest(store, "rev-b-schedule")
    embed_document(store, document_id, embed=embed, model_id=model_id)
    add_summary_chunk(store, document_id, "A summary written later.")
    asked = []

    def watching(texts):
        asked.extend(texts)
        return embed(texts)

    result = embed_document(store, document_id, embed=watching, model_id=model_id)

    assert asked == ["A summary written later."]
    assert result.written == 1


def test_recomputing_is_available_when_it_is_asked_for(store, ingest, fake_embedder):
    embed, model_id = fake_embedder
    document_id = ingest(store, "rev-b-schedule")
    embed_document(store, document_id, embed=embed, model_id=model_id)

    def other(texts):
        return np.ones((len(texts), 4), dtype=np.float32)

    result = embed_document(
        store, document_id, recompute=True, embed=other, model_id="other-embedder"
    )

    assert result.written == len(rows(store, document_id))
    assert result.dimension == 4
    assert {row["embedding_model"] for row in rows(store, document_id)} == {
        "other-embedder"
    }


def test_an_embedder_given_without_its_identifier_is_refused(store, ingest):
    document_id = ingest(store, "rev-b-schedule")

    with pytest.raises(ValueError, match="model_id has to be given"):
        embed_document(store, document_id, embed=lambda texts: np.zeros((1, 3)))


def test_a_wrong_number_of_vectors_is_refused(store, ingest):
    turns = [
        {"speaker": "Priya", "text": f"Point number {index} about the boards."}
        for index in range(40)
    ]
    document_id = ingest(store, "long", turns=turns)
    assert len(rows(store, document_id)) > 1, "the fixture needs several chunks"

    with pytest.raises(ValueError, match="returned 1 vectors"):
        embed_document(
            store,
            document_id,
            embed=lambda texts: np.zeros((1, 3), dtype=np.float32),
            model_id="short-embedder",
        )


def test_a_document_with_nothing_to_embed_reports_that(store, ingest, fake_embedder):
    embed, model_id = fake_embedder
    document_id = ingest(store, "rev-b-schedule")
    store.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    result = embed_document(store, document_id, embed=embed, model_id=model_id)

    assert result == type(result)(written=0, skipped=0, model_id=None, dimension=None)


def test_the_default_embedder_is_the_projects_and_is_recorded_as_such(
    store, ingest, monkeypatch
):
    """Cover the default path without installing torch.

    ``embed.py`` imports the embedder lazily, so a stand-in module put in
    ``sys.modules`` is enough to prove that what it reaches for is the
    passage-side function and the identifier beside it.
    """
    import sys
    import types

    module = types.ModuleType("corpus_query.models.embedder")
    module.EMBEDDING_MODEL_ID = "stand-in/bge"
    module.embed_documents = lambda texts: np.ones((len(texts), 2), dtype=np.float32)
    monkeypatch.setitem(sys.modules, "corpus_query.models.embedder", module)
    document_id = ingest(store, "rev-b-schedule")

    result = embed_document(store, document_id)

    assert result.model_id == "stand-in/bge"
    assert result.dimension == 2
