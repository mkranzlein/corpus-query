"""Loading and calling the reranking model.

This module only exposes the reranker; it does not decide when to call it or
what to feed it. That decision belongs to the ranking pipeline that
combines dense and lexical retrieval, which is out of scope here.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from corpus_query.models.hf_home import ensure_hf_home

ensure_hf_home()

from sentence_transformers import CrossEncoder  # noqa: E402

#: Identifier passed to sentence-transformers.
RERANKER_MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def load_reranker() -> CrossEncoder:
    """Load the reranking model, once.

    Cached so that every caller in the process shares one loaded model
    instead of reloading it per call.

    Returns:
        A ready-to-use :class:`CrossEncoder`.
    """
    return CrossEncoder(RERANKER_MODEL_ID)


def score(
    query: str, documents: Sequence[str], model: CrossEncoder | None = None
) -> list[float]:
    """Score how relevant each document is to a query.

    Args:
        query: The search query.
        documents: Candidate passages, such as chunk text, to score against
            the query.
        model: The model to score with. Defaults to :func:`load_reranker`.
            Overridable in tests so a fake model can stand in for the real
            one.

    Returns:
        One relevance score per document, in the same order. Higher means
        more relevant; scores are not bounded to a fixed range.
    """
    model = model if model is not None else load_reranker()
    pairs = [(query, document) for document in documents]
    return [float(x) for x in model.predict(pairs)]
