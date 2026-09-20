"""Loading and calling the embedding model.

bge is an asymmetric embedder: it was trained so that a query and the
passage it should retrieve end up close in vector space only when the query
carries an instruction prefix and the passage does not. Embedding a query
bare, or a passage with the prefix, still produces a vector — there is no
error — it just retrieves worse, silently. :func:`embed_queries` and
:func:`embed_documents` are kept as separate functions so that mistake
requires calling the wrong one, not forgetting an argument.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

import numpy as np

from corpus_query.models.hf_home import ensure_hf_home

ensure_hf_home()

from sentence_transformers import SentenceTransformer  # noqa: E402

#: Identifier passed to sentence-transformers, and recorded alongside every
#: vector this model produces so a later change of embedder is detectable.
EMBEDDING_MODEL_ID = "BAAI/bge-small-en-v1.5"

#: Dimensionality of every vector this model produces.
EMBEDDING_DIM = 384

#: bge's instruction prefix for the query side of an asymmetric search.
#: Passages are embedded without it.
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

#: Texts per call to the model's ``encode``. Keeps memory bounded on a large
#: batch while still avoiding one call per text.
_BATCH_SIZE = 32


@lru_cache(maxsize=1)
def load_embedder() -> SentenceTransformer:
    """Load the embedding model, once.

    Cached so that every caller in the process shares one loaded model
    instead of reloading it per call.

    Returns:
        A ready-to-use :class:`SentenceTransformer`.
    """
    return SentenceTransformer(EMBEDDING_MODEL_ID)


def embed_queries(
    texts: Sequence[str], model: SentenceTransformer | None = None
) -> np.ndarray:
    """Embed search queries, with bge's instruction prefix applied.

    Args:
        texts: The queries to embed.
        model: The model to embed with. Defaults to :func:`load_embedder`.
            Overridable in tests so a fake model can stand in for the real
            one.

    Returns:
        An array of shape ``(len(texts), EMBEDDING_DIM)``, one row per
        query, in order.
    """
    model = model if model is not None else load_embedder()
    prefixed = [f"{_QUERY_PREFIX}{text}" for text in texts]
    return np.asarray(
        model.encode(
            prefixed,
            batch_size=_BATCH_SIZE,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
    )


def embed_documents(
    texts: Sequence[str], model: SentenceTransformer | None = None
) -> np.ndarray:
    """Embed passages, bare, with no instruction prefix.

    Args:
        texts: The passages to embed, such as chunk text.
        model: The model to embed with. Defaults to :func:`load_embedder`.
            Overridable in tests so a fake model can stand in for the real
            one.

    Returns:
        An array of shape ``(len(texts), EMBEDDING_DIM)``, one row per
        passage, in order.
    """
    model = model if model is not None else load_embedder()
    return np.asarray(
        model.encode(
            list(texts),
            batch_size=_BATCH_SIZE,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
    )
