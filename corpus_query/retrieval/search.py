"""The retrieval pipeline: a query in, ranked chunks and their metadata out.

BM25 and dense search each propose ~``candidates`` chunks, RRF fuses the two
rankings into one, and a cross-encoder reranks the fused candidates down to
``results``. What comes back carries everything a citation needs — where the
text came from — and the confidence signals a later exercise's agent will
read, not threshold.

Importing :mod:`corpus_query.models.reranker` pulls in torch, which is an
optional extra. It is imported when reranking is actually asked for rather
than at module scope, so a caller that supplies its own ``rerank`` runs
without the extra installed, the same pattern :mod:`corpus_query.enrich.embed`
and :mod:`corpus_query.retrieval.dense` use.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from chromadb.api.models.Collection import Collection

from corpus_query import tracing
from corpus_query.retrieval.dense import EmbedQueries, search_dense
from corpus_query.retrieval.fuse import RRF_RANK_CONSTANT, reciprocal_rank_fusion
from corpus_query.retrieval.lexical import search_lexical, unmatched_terms

#: Scores a query against candidate chunk texts, one score per text, in
#: order. Higher is more relevant.
type RerankScore = Callable[[str, Sequence[str]], Sequence[float]]

#: How many candidates BM25 and dense search each propose, and how many
#: results the cross-encoder narrows them down to, when a caller does not
#: say otherwise.
DEFAULT_CANDIDATES = 50
DEFAULT_RESULTS = 5


@dataclass(frozen=True)
class Result:
    """One chunk returned by a search, with what a citation needs and why
    it ranked where it did."""

    chunk_id: int
    text: str
    document_slug: str
    source_kind: str
    """What the document was read out of, from
    :mod:`corpus_query.store.kinds`."""

    title: str
    document_date: str
    author: str | None
    """Who wrote it, or ``None`` for a transcript, whose people are its
    attendees."""

    attendees: list[str]
    """Who was in the room, for a transcript. Empty for a document with an
    author. The two coexist rather than one standing in for the other, so a
    caller asking who to ask about a passage has the same answer either
    way."""

    location: str
    """What a citation shows a reader: a turn range, a heading path, a slide
    number."""

    span_start: int | None
    span_end: int | None
    topics: list[str]
    time_sensitivity: str | None
    business_impact: str | None
    rerank_score: float
    rank: int
    """1-indexed position in the returned results, best first."""


@dataclass(frozen=True)
class Confidence:
    """Signals about how confidently a search's top results answer the
    query. Reported, not thresholded — deciding what counts as too weak is
    an agent's job, not this pipeline's."""

    top_score: float | None
    """The top result's rerank score, or ``None`` when there were no
    candidates to rerank."""

    margin: float | None
    """The gap between the first and second result's rerank score, or
    ``None`` when fewer than two results came back."""

    lexical_dense_agree: bool
    """Whether BM25 and dense search independently put the same chunk
    first, before fusion or reranking touched either ranking."""

    unmatched_terms: list[str]
    """Query terms that matched no chunk at all in the lexical search —
    typically a misspelling or a name the corpus does not have."""


@dataclass(frozen=True)
class SearchResult:
    """What a search returns: ranked results and the confidence in them."""

    results: list[Result]
    confidence: Confidence


def search(
    connection: sqlite3.Connection,
    collection: Collection,
    query: str,
    candidates: int = DEFAULT_CANDIDATES,
    results: int = DEFAULT_RESULTS,
    rrf_k: int = RRF_RANK_CONSTANT,
    embed: EmbedQueries | None = None,
    rerank: RerankScore | None = None,
) -> SearchResult:
    """Run the hybrid retrieval pipeline for one query.

    Args:
        connection: An open document store.
        collection: The open vector index, as returned by
            :func:`corpus_query.retrieval.index.open_index`.
        query: The raw user query.
        candidates: How many chunks BM25 and dense search each propose
            before fusion.
        results: How many fused candidates the reranker keeps.
        rrf_k: The RRF rank constant. See
            :data:`corpus_query.retrieval.fuse.RRF_RANK_CONSTANT`.
        embed: What to embed the query with, for dense search. Defaults to
            the project's query-side embedder. Overridable in tests.
        rerank: What to score fused candidates with. Defaults to the
            project's cross-encoder. Overridable in tests.

    Returns:
        The ranked results and the confidence signals about them.
    """
    with tracing.span(
        "retrieval corpus",
        {
            tracing.OPERATION: "retrieval",
            tracing.DATA_SOURCE: "corpus",
            tracing.RETRIEVAL_TOP_K: results,
            tracing.RETRIEVAL_QUERY: query,
            "corpus_query.retrieval.candidates": candidates,
        },
    ) as searching:
        result, ranks = _search(
            connection, collection, query, candidates, results, rrf_k, embed, rerank
        )
        tracing.annotate(searching, _explained(result, ranks))
        return result


def _search(
    connection: sqlite3.Connection,
    collection: Collection,
    query: str,
    candidates: int,
    results: int,
    rrf_k: int,
    embed: EmbedQueries | None,
    rerank: RerankScore | None,
) -> tuple[SearchResult, dict[str, dict[int, int]]]:
    """Run the pipeline, with a span around each stage.

    Arguments are :func:`search`'s.

    Returns:
        The search's result, and where each chunk stood in the lexical,
        dense, and fused rankings, by chunk id, for the span that explains
        the result.
    """
    with tracing.span(
        "lexical_search", {"corpus_query.retrieval.limit": candidates}
    ) as lexical:
        lexical_hits = search_lexical(connection, query, limit=candidates)
        missing_terms = unmatched_terms(connection, query)
        tracing.annotate(
            lexical,
            {
                "corpus_query.retrieval.hit_count": len(lexical_hits),
                "corpus_query.retrieval.top_score": (
                    lexical_hits[0].score if lexical_hits else None
                ),
                "corpus_query.retrieval.unmatched_terms": missing_terms,
            },
        )
    dense_hits = search_dense(collection, query, limit=candidates, embed=embed)
    lexical_ranking = [hit.chunk_id for hit in lexical_hits]
    dense_ranking = [hit.chunk_id for hit in dense_hits]

    lexical_dense_agree = bool(
        lexical_ranking and dense_ranking and lexical_ranking[0] == dense_ranking[0]
    )

    with tracing.span("fuse", {"corpus_query.fusion.rrf_k": rrf_k}) as fusing:
        fused = reciprocal_rank_fusion([lexical_ranking, dense_ranking], k=rrf_k)
        tracing.annotate(
            fusing,
            {
                "corpus_query.retrieval.hit_count": len(fused),
                "corpus_query.retrieval.top_score": fused[0][1] if fused else None,
            },
        )
    candidate_ids = [chunk_id for chunk_id, _ in fused]
    ranks = {
        "lexical": _positions(lexical_ranking),
        "dense": _positions(dense_ranking),
        "fused": _positions(candidate_ids),
    }

    if not candidate_ids:
        return SearchResult(
            results=[],
            confidence=Confidence(
                top_score=None,
                margin=None,
                lexical_dense_agree=lexical_dense_agree,
                unmatched_terms=missing_terms,
            ),
        ), ranks

    rerank_model = None
    if rerank is None:
        rerank = _project_rerank()
        rerank_model = _project_rerank_model()
    with tracing.span(
        "rerank",
        {
            "corpus_query.rerank.model": rerank_model,
            "corpus_query.rerank.candidate_count": len(candidate_ids),
        },
    ) as reranking:
        texts = _chunk_texts(connection, candidate_ids)
        scores = list(rerank(query, [texts[chunk_id] for chunk_id in candidate_ids]))
        ranked = sorted(
            zip(candidate_ids, scores, strict=True),
            key=lambda pair: pair[1],
            reverse=True,
        )
        top = ranked[:results]
        tracing.annotate(
            reranking,
            {
                "corpus_query.retrieval.hit_count": len(top),
                "corpus_query.retrieval.top_score": top[0][1] if top else None,
            },
        )

    metadata = _chunk_metadata(connection, [chunk_id for chunk_id, _ in top])
    result_rows = [
        Result(
            chunk_id=chunk_id,
            text=metadata[chunk_id].text,
            document_slug=metadata[chunk_id].document_slug,
            source_kind=metadata[chunk_id].source_kind,
            title=metadata[chunk_id].title,
            document_date=metadata[chunk_id].document_date,
            author=metadata[chunk_id].author,
            attendees=metadata[chunk_id].attendees,
            location=metadata[chunk_id].location,
            span_start=metadata[chunk_id].span_start,
            span_end=metadata[chunk_id].span_end,
            topics=metadata[chunk_id].topics,
            time_sensitivity=metadata[chunk_id].time_sensitivity,
            business_impact=metadata[chunk_id].business_impact,
            rerank_score=score,
            rank=rank,
        )
        for rank, (chunk_id, score) in enumerate(top, start=1)
    ]

    top_score = result_rows[0].rerank_score if result_rows else None
    margin = (
        result_rows[0].rerank_score - result_rows[1].rerank_score
        if len(result_rows) >= 2
        else None
    )

    return SearchResult(
        results=result_rows,
        confidence=Confidence(
            top_score=top_score,
            margin=margin,
            lexical_dense_agree=lexical_dense_agree,
            unmatched_terms=missing_terms,
        ),
    ), ranks


def _positions(ranking: Sequence[int]) -> dict[int, int]:
    """Map each chunk in a ranking to its 1-indexed position in it."""
    return {chunk_id: position for position, chunk_id in enumerate(ranking, 1)}


def _explained(
    result: SearchResult, ranks: dict[str, dict[int, int]]
) -> dict[str, Any]:
    """Describe a search's result, as the attributes of its span.

    Each list is parallel to the results, best first, so the n-th entry of
    each is about the n-th passage returned: which chunk it was, what the
    reranker scored it, and where lexical search, dense search, and fusion
    had put it before the reranker saw it. A position of 0 means that side
    did not propose the chunk at all. Together they say why a chunk ranked
    where it did — a passage the reranker lifted from fifteenth, or one
    only one side found.

    The confidence signals are the ones the search already computed,
    carried over as they are.

    Args:
        result: What the search returned.
        ranks: Where each chunk stood in each ranking.

    Returns:
        The attributes.
    """
    chunk_ids = [row.chunk_id for row in result.results]
    return {
        "corpus_query.retrieval.result_count": len(result.results),
        "corpus_query.retrieval.chunk_ids": chunk_ids,
        "corpus_query.retrieval.document_slugs": [
            row.document_slug for row in result.results
        ],
        "corpus_query.retrieval.rerank_scores": [
            float(row.rerank_score) for row in result.results
        ],
        **{
            f"corpus_query.retrieval.{side}_ranks": [
                ranks[side].get(chunk_id, 0) for chunk_id in chunk_ids
            ]
            for side in ("lexical", "dense", "fused")
        },
        **tracing.confidence_attributes(asdict(result.confidence)),
    }


@dataclass(frozen=True)
class Chunk:
    """A chunk's text and everything needed for a result and a citation.

    What a search result carries apart from its ranking, which is what a
    reader opening one cited passage wants to see.
    """

    text: str
    document_slug: str
    source_kind: str
    title: str
    document_date: str
    author: str | None
    attendees: list[str]
    location: str
    span_start: int | None
    span_end: int | None
    topics: list[str]
    time_sensitivity: str | None
    business_impact: str | None


def read_chunk(connection: sqlite3.Connection, chunk_id: int) -> Chunk | None:
    """Read one chunk by id, with its document's provenance and metadata.

    An answer's citations carry where a passage came from but not its text,
    so a reader opening one needs to read the passage back by id. It is read
    here, with the same query a search result is built from, so the two
    cannot disagree about what a chunk says or where it sits.

    Args:
        connection: An open document store.
        chunk_id: The chunk to read.

    Returns:
        The chunk, or ``None`` if the store holds no chunk with that id.
    """
    return _chunk_metadata(connection, [chunk_id]).get(chunk_id)


def _chunk_texts(
    connection: sqlite3.Connection, chunk_ids: Sequence[int]
) -> dict[int, str]:
    """Fetch chunk text for a set of chunk ids, for reranking.

    Args:
        connection: An open document store.
        chunk_ids: The chunks to fetch text for.

    Returns:
        Chunk text keyed by chunk id.
    """
    placeholders = ", ".join("?" for _ in chunk_ids)
    rows = connection.execute(
        f"SELECT id, text FROM chunks WHERE id IN ({placeholders})",
        list(chunk_ids),
    ).fetchall()
    return {row["id"]: row["text"] for row in rows}


def _chunk_metadata(
    connection: sqlite3.Connection, chunk_ids: Sequence[int]
) -> dict[int, Chunk]:
    """Fetch everything a result needs about a set of chunks.

    Args:
        connection: An open document store.
        chunk_ids: The chunks to fetch metadata for, typically just the
            handful that survived reranking.

    Returns:
        Metadata keyed by chunk id.
    """
    if not chunk_ids:
        return {}
    placeholders = ", ".join("?" for _ in chunk_ids)
    rows = connection.execute(
        f"""
        SELECT
            chunks.id AS chunk_id,
            chunks.text AS text,
            chunks.location AS location,
            chunks.span_start AS span_start,
            chunks.span_end AS span_end,
            documents.id AS document_id,
            documents.slug AS document_slug,
            documents.source_kind AS source_kind,
            documents.title AS title,
            documents.document_date AS document_date,
            documents.author AS author,
            documents.time_sensitivity AS time_sensitivity,
            documents.business_impact AS business_impact
        FROM chunks
        JOIN documents ON documents.id = chunks.document_id
        WHERE chunks.id IN ({placeholders})
        """,
        list(chunk_ids),
    ).fetchall()
    document_ids = [row["document_id"] for row in rows]
    topics_by_document = _topics_by_document(connection, document_ids)
    attendees_by_document = _attendees_by_document(connection, document_ids)
    return {
        row["chunk_id"]: Chunk(
            text=row["text"],
            document_slug=row["document_slug"],
            source_kind=row["source_kind"],
            title=row["title"],
            document_date=row["document_date"],
            author=row["author"],
            attendees=attendees_by_document.get(row["document_id"], []),
            location=row["location"],
            span_start=row["span_start"],
            span_end=row["span_end"],
            topics=topics_by_document.get(row["document_id"], []),
            time_sensitivity=row["time_sensitivity"],
            business_impact=row["business_impact"],
        )
        for row in rows
    }


def _attendees_by_document(
    connection: sqlite3.Connection, document_ids: Sequence[int]
) -> dict[int, list[str]]:
    """Fetch who was at each document's meeting.

    Args:
        connection: An open document store.
        document_ids: The documents to fetch attendees for.

    Returns:
        Attendee names, in the order they were written, keyed by document
        id. A document that has an author instead of attendees is absent.
    """
    if not document_ids:
        return {}
    placeholders = ", ".join("?" for _ in document_ids)
    rows = connection.execute(
        f"""
        SELECT document_id, name
        FROM attendees
        WHERE document_id IN ({placeholders})
        ORDER BY id
        """,
        list(document_ids),
    ).fetchall()
    by_document: dict[int, list[str]] = {}
    for row in rows:
        by_document.setdefault(row["document_id"], []).append(row["name"])
    return by_document


def _topics_by_document(
    connection: sqlite3.Connection, document_ids: Sequence[int]
) -> dict[int, list[str]]:
    """Fetch each document's topic names.

    Args:
        connection: An open document store.
        document_ids: The documents to fetch topics for.

    Returns:
        Topic names, in no particular order, keyed by document id.
    """
    if not document_ids:
        return {}
    placeholders = ", ".join("?" for _ in document_ids)
    rows = connection.execute(
        f"""
        SELECT document_topics.document_id AS document_id, topics.name AS name
        FROM document_topics
        JOIN topics ON topics.id = document_topics.topic_id
        WHERE document_topics.document_id IN ({placeholders})
        """,
        list(document_ids),
    ).fetchall()
    by_document: dict[int, list[str]] = {}
    for row in rows:
        by_document.setdefault(row["document_id"], []).append(row["name"])
    return by_document


def _project_rerank() -> RerankScore:
    """Return the project's cross-encoder scoring function.

    Returns:
        :func:`~corpus_query.models.reranker.score`.
    """
    from corpus_query.models.reranker import score

    return score


def _project_rerank_model() -> str:
    """Return the name of the project's cross-encoder, for its span.

    Returns:
        :data:`~corpus_query.models.reranker.RERANKER_MODEL_ID`.
    """
    from corpus_query.models.reranker import RERANKER_MODEL_ID

    return RERANKER_MODEL_ID
