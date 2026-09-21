"""Vector search over the Chroma index.

The query has to be embedded through the query side of the embedder — the
prefixed path, :func:`~corpus_query.models.embedder.embed_queries` — because
bge is asymmetric. Embedding a query the way a chunk is embedded still
returns a vector and Chroma still returns hits; it just retrieves worse, with
nothing anywhere reporting the mistake. See
:mod:`corpus_query.models.embedder` for why the two sides are kept apart.

Importing :mod:`corpus_query.models.embedder` pulls in torch, which is an
optional extra. It is imported when a query is actually embedded rather than
at module scope, so a caller that supplies its own ``embed`` runs without the
extra installed — the pattern :mod:`corpus_query.enrich.embed` uses for the
same reason.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from chromadb.api.models.Collection import Collection

from corpus_query import tracing

#: Embeds search queries: takes query texts, returns one vector per text, in
#: order, with the query-side prefix already applied.
type EmbedQueries = Callable[[Sequence[str]], np.ndarray]


@dataclass(frozen=True)
class DenseHit:
    """One chunk the vector index matched, and how well."""

    chunk_id: int
    score: float
    """Cosine similarity: higher is better, matching the lexical side. The
    index is configured for cosine distance, so this is ``1 - distance``."""


def search_dense(
    collection: Collection,
    query: str,
    limit: int = 50,
    embed: EmbedQueries | None = None,
) -> list[DenseHit]:
    """Rank chunks against a query by cosine similarity in the vector index.

    Args:
        collection: The open Chroma collection to search, as returned by
            :func:`corpus_query.retrieval.index.open_index`.
        query: The raw user query.
        limit: The most hits to return.
        embed: What to embed the query with. Defaults to the project's
            query-side embedder. Overridable in tests so a fixed vector can
            stand in for a loaded model.

    Returns:
        Hits ordered best first. Empty when the index holds nothing.
    """
    model_id = None
    if embed is None:
        embed = _project_embed_queries()
        model_id = _project_embedding_model()
    with tracing.span(
        f"embeddings {model_id}" if model_id else "embeddings",
        {
            tracing.OPERATION: "embeddings",
            tracing.PROVIDER: "sentence_transformers" if model_id else None,
            tracing.REQUEST_MODEL: model_id,
        },
    ) as embedding:
        [vector] = np.asarray(embed([query]))
        embedding.set_attribute(tracing.EMBEDDING_DIMENSIONS, int(vector.shape[0]))
    with tracing.span("dense_search", {"corpus_query.retrieval.limit": limit}) as found:
        hits = _query(collection, vector, limit)
        tracing.annotate(
            found,
            {
                "corpus_query.retrieval.hit_count": len(hits),
                "corpus_query.retrieval.top_score": hits[0].score if hits else None,
            },
        )
    return hits


def _query(collection: Collection, vector: np.ndarray, limit: int) -> list[DenseHit]:
    """Ask the index for the chunks nearest a query vector.

    Args:
        collection: The open Chroma collection.
        vector: The embedded query.
        limit: The most hits to return.

    Returns:
        Hits ordered best first. Empty when the index holds nothing.
    """
    if collection.count() == 0:
        return []
    result = collection.query(
        query_embeddings=[vector.tolist()],
        n_results=min(limit, collection.count()),
    )
    ids = result["ids"][0]
    distances = result["distances"][0]
    return [
        DenseHit(chunk_id=int(chunk_id), score=1.0 - distance)
        for chunk_id, distance in zip(ids, distances, strict=True)
    ]


def _project_embed_queries() -> EmbedQueries:
    """Return the project's query-side embedding function.

    Returns:
        :func:`~corpus_query.models.embedder.embed_queries`.
    """
    from corpus_query.models.embedder import embed_queries

    return embed_queries


def _project_embedding_model() -> str:
    """Return the name of the project's embedding model, for its span.

    Returns:
        :data:`~corpus_query.models.embedder.EMBEDDING_MODEL_ID`.
    """
    from corpus_query.models.embedder import EMBEDDING_MODEL_ID

    return EMBEDDING_MODEL_ID
