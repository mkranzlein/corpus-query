"""Tests for the reranking model.

Stubbed like the embedder tests: no weights loaded, no network call, except
for one real-load test skipped unless the weights are already cached.
"""

from __future__ import annotations

import pytest

#: Importing the module under test imports sentence-transformers, and
#: with it torch. Skip the whole file when the models extra is not
#: installed, which is how CI runs it — without this the import below
#: would fail at collection, before the slow mark could deselect
#: anything.
pytest.importorskip("sentence_transformers")

#: Marked at module scope rather than on the real-load test alone: the
#: stubs are cheap, but importing torch to run them is not.
pytestmark = pytest.mark.slow

from corpus_query.models import reranker  # noqa: E402
from corpus_query.models.reranker import (  # noqa: E402
    RERANKER_MODEL_ID,
    load_reranker,
    score,
)


class FakeCrossEncoder:
    """Stands in for a :class:`sentence_transformers.CrossEncoder`."""

    def __init__(self):
        self.calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs):
        self.calls.append(list(pairs))
        # Score by shared word count, just something to assert on.
        return [
            float(len(set(query.split()) & set(document.split())))
            for query, document in pairs
        ]


def test_score_pairs_query_with_each_document_in_order():
    model = FakeCrossEncoder()

    scores = score(
        "connector lead time",
        ["connector lead time update", "unrelated notes"],
        model=model,
    )

    assert scores == [3.0, 0.0]
    assert model.calls[0] == [
        ("connector lead time", "connector lead time update"),
        ("connector lead time", "unrelated notes"),
    ]


def test_score_returns_plain_floats():
    model = FakeCrossEncoder()

    [result] = score("a", ["a"], model=model)

    assert isinstance(result, float)


def test_model_identifier_is_exposed():
    assert RERANKER_MODEL_ID == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_load_reranker_is_cached(monkeypatch):
    load_reranker.cache_clear()
    built = []

    class FakeCrossEncoderClass:
        def __init__(self, model_id):
            built.append(model_id)

    monkeypatch.setattr(reranker, "CrossEncoder", FakeCrossEncoderClass)

    first = load_reranker()
    second = load_reranker()

    assert first is second
    assert built == [RERANKER_MODEL_ID]
    load_reranker.cache_clear()


def test_real_reranker_load_and_scoring(monkeypatch):
    from huggingface_hub.errors import LocalEntryNotFoundError

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    load_reranker.cache_clear()
    try:
        model = load_reranker()
    except OSError, LocalEntryNotFoundError:
        pytest.skip("reranker weights are not in the local cache")
    finally:
        load_reranker.cache_clear()

    scores = score("connector lead time", ["connector lead time update"], model=model)

    assert len(scores) == 1
