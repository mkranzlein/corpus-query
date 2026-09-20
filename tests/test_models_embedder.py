"""Tests for the embedding model.

These stub sentence-transformers: no weights are loaded and no network call
is made. The one test that loads the real model is skipped unless it is
already sitting in the local Hugging Face cache, so it never triggers a
download on its own.
"""

from __future__ import annotations

import numpy as np
import pytest

from corpus_query.models import embedder
from corpus_query.models.embedder import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_ID,
    embed_documents,
    embed_queries,
    load_embedder,
)


class FakeEmbeddingModel:
    """Stands in for a :class:`sentence_transformers.SentenceTransformer`."""

    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def encode(self, texts, **kwargs):
        self.calls.append({"texts": list(texts), **kwargs})
        # One deterministic vector per text, distinguishable by content.
        return np.array([_fake_vector(text) for text in texts])


def _fake_vector(text: str) -> np.ndarray:
    """A cheap stand-in embedding: distinct for distinct text."""
    vector = np.zeros(EMBEDDING_DIM)
    vector[hash(text) % EMBEDDING_DIM] = 1.0
    return vector


def test_query_prefix_differs_from_bare_document_text():
    model = FakeEmbeddingModel()

    [query_vector] = embed_queries(["hardware supply"], model=model)
    [document_vector] = embed_documents(["hardware supply"], model=model)

    assert not np.array_equal(query_vector, document_vector)
    assert embedder._QUERY_PREFIX in model.calls[0]["texts"][0]
    assert model.calls[1]["texts"][0] == "hardware supply"


def test_embedding_is_batched_not_one_call_per_text():
    model = FakeEmbeddingModel()

    embed_documents(["a", "b", "c"], model=model)

    assert len(model.calls) == 1
    assert model.calls[0]["texts"] == ["a", "b", "c"]


def test_embed_queries_returns_one_vector_per_text():
    model = FakeEmbeddingModel()

    vectors = embed_queries(["one", "two"], model=model)

    assert vectors.shape == (2, EMBEDDING_DIM)


def test_model_identifier_and_dimension_are_exposed():
    assert EMBEDDING_MODEL_ID == "BAAI/bge-small-en-v1.5"
    assert EMBEDDING_DIM == 384


def test_load_embedder_is_cached(monkeypatch):
    load_embedder.cache_clear()
    built = []

    class FakeSentenceTransformer:
        def __init__(self, model_id):
            built.append(model_id)

    monkeypatch.setattr(embedder, "SentenceTransformer", FakeSentenceTransformer)

    first = load_embedder()
    second = load_embedder()

    assert first is second
    assert built == [EMBEDDING_MODEL_ID]
    load_embedder.cache_clear()


@pytest.mark.slow
def test_real_embedder_load_and_prefix_behavior(monkeypatch):
    from huggingface_hub.errors import LocalEntryNotFoundError

    # Offline mode: this proves the model loads for real, from whatever is
    # already cached, without ever attempting a network call of its own.
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    load_embedder.cache_clear()
    try:
        model = load_embedder()
    except OSError, LocalEntryNotFoundError:
        pytest.skip("bge weights are not in the local cache")
    finally:
        load_embedder.cache_clear()

    [query_vector] = embed_queries(["hardware supply"], model=model)
    [document_vector] = embed_documents(["hardware supply"], model=model)

    assert query_vector.shape == (EMBEDDING_DIM,)
    assert not np.array_equal(query_vector, document_vector)
