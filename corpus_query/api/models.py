"""Request and response shapes for the query API.

These models are the contract. Every field a caller could want is generated
into the OpenAPI schema from here rather than described in prose somewhere
else, so what ``/docs`` says and what the endpoint returns cannot drift apart.

The contract starts at this shape. From here it grows by addition: a field
that exists keeps its name and its meaning; something new gets a new field,
and a field that stops being produced goes null rather than being reused for
something else. Later work reads this shape — the agent that synthesizes an
answer out of these results is written against it — and the price of that
discipline is a field or two nobody reads yet, which is far cheaper than a
silent change of meaning.

It starts here rather than earlier because generalizing the store past
transcripts renamed two of these fields, while nothing consumed the endpoint
yet. A ``meeting_date`` on a spec document would have been a field whose
meaning had already drifted, which is exactly what the rule above exists to
prevent; renaming it once, before there was a caller, was the cheaper of the
two.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from corpus_query.retrieval.search import DEFAULT_RESULTS, Confidence, Result

#: The most results one request may ask for. The cross-encoder scores every
#: fused candidate, so an unbounded limit is an unbounded request.
MAX_RESULTS = 50


class SearchRequest(BaseModel):
    """A natural-language question to run against the corpus."""

    query: str = Field(
        description="The question, in natural language.",
        examples=["What did we decide about the connector lead time?"],
    )
    limit: int = Field(
        default=DEFAULT_RESULTS,
        ge=1,
        le=MAX_RESULTS,
        description="How many ranked results to return.",
    )

    @field_validator("query")
    @classmethod
    def _reject_empty(cls, value: str) -> str:
        """Reject a query that is empty or only whitespace.

        A blank query is not a search for nothing, it is a caller that lost
        its input somewhere. Saying so is more useful than ranking the whole
        corpus against an empty string.

        Args:
            value: The submitted query.

        Returns:
            The query, with surrounding whitespace removed.

        Raises:
            ValueError: If nothing but whitespace was submitted.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty")
        return stripped


class SearchResultModel(BaseModel):
    """One ranked chunk: its text, where it came from, and why it ranked."""

    rank: int = Field(description="1-indexed position, best first.")
    chunk_id: int = Field(description="Row id of the chunk in the store.")
    text: str = Field(description="The chunk's text.")
    document_slug: str = Field(description="Slug of the document it came from.")
    source_kind: str = Field(
        description="What the document was read out of: transcript, docx, "
        "pptx, or xlsx."
    )
    title: str = Field(description="The document's title, or a meeting's subject.")
    document_date: str = Field(description="The document's date, ISO 8601.")
    author: str | None = Field(
        description="Who wrote it, or null for a transcript, which has "
        "attendees rather than an author."
    )
    location: str = Field(
        description="Where in the document the chunk sits, as a citation "
        "shows it: a turn range, a heading path, a slide number, a sheet and "
        "row range."
    )
    span_start: int | None = Field(
        description="First unit the chunk covers, counted in whatever its "
        "format counts in. Null for a chunk written about the document "
        "rather than cut out of it."
    )
    span_end: int | None = Field(
        description="Last unit the chunk covers, inclusive. Null alongside span_start."
    )
    topics: list[str] = Field(description="Topics assigned to the document.")
    time_sensitivity: str | None = Field(
        description="How time sensitive the document is, as enrichment judged it."
    )
    business_impact: str | None = Field(
        description="How much business impact the document carries."
    )
    rerank_score: float = Field(
        description="The cross-encoder's score. Higher is more relevant; the "
        "scale is the model's own and is not bounded."
    )

    @classmethod
    def from_result(cls, result: Result) -> SearchResultModel:
        """Build the response shape from a retrieval result.

        Args:
            result: One result from the retrieval pipeline.

        Returns:
            The same result, as the API reports it.
        """
        return cls(
            rank=result.rank,
            chunk_id=result.chunk_id,
            text=result.text,
            document_slug=result.document_slug,
            source_kind=result.source_kind,
            title=result.title,
            document_date=result.document_date,
            author=result.author,
            location=result.location,
            span_start=result.span_start,
            span_end=result.span_end,
            topics=list(result.topics),
            time_sensitivity=result.time_sensitivity,
            business_impact=result.business_impact,
            rerank_score=result.rerank_score,
        )


class ConfidenceModel(BaseModel):
    """How confidently the top results answer the query.

    Reported, never thresholded. What counts as too weak to act on is the
    caller's decision, and this endpoint does not make it for them.
    """

    top_score: float | None = Field(
        description="The top result's rerank score, or null with no results."
    )
    margin: float | None = Field(
        description="Gap between the first and second rerank score, or null "
        "with fewer than two results."
    )
    lexical_dense_agree: bool = Field(
        description="Whether BM25 and vector search independently ranked the "
        "same chunk first, before fusion and reranking."
    )
    unmatched_terms: list[str] = Field(
        description="Query terms that matched no chunk lexically — typically "
        "a misspelling, or a name the corpus does not have."
    )

    @classmethod
    def from_confidence(cls, confidence: Confidence) -> ConfidenceModel:
        """Build the response shape from the pipeline's signals.

        Args:
            confidence: The confidence signals from one search.

        Returns:
            The same signals, as the API reports them.
        """
        return cls(
            top_score=confidence.top_score,
            margin=confidence.margin,
            lexical_dense_agree=confidence.lexical_dense_agree,
            unmatched_terms=list(confidence.unmatched_terms),
        )


class SearchResponse(BaseModel):
    """What ``POST /search`` returns: ranked passages, not an answer."""

    query: str = Field(description="The query as it was run, whitespace trimmed.")
    results: list[SearchResultModel] = Field(
        description="Ranked results, best first. Empty when nothing matched."
    )
    confidence: ConfidenceModel = Field(
        description="Signals about those results, for the caller to weigh."
    )


class DatabaseHealth(BaseModel):
    """Whether the document store answered, and what it holds."""

    readable: bool = Field(description="Whether a query against it succeeded.")
    chunks: int | None = Field(
        default=None, description="Chunks in the store, or null if unreadable."
    )


class IndexHealth(BaseModel):
    """Whether the vector index is open, and what it holds."""

    loaded: bool = Field(description="Whether the collection answered.")
    vectors: int | None = Field(
        default=None, description="Vectors in the index, or null if unreadable."
    )


class HealthResponse(BaseModel):
    """What ``GET /health`` returns."""

    status: str = Field(
        description='"ok" when both answered, "degraded" when either did not.'
    )
    database: DatabaseHealth
    index: IndexHealth


class AnswerRequest(BaseModel):
    """A question to answer out of the corpus."""

    question: str = Field(
        description="The question, in natural language.",
        examples=["What did we decide about the connector lead time?"],
    )
    thread_id: str | None = Field(
        default=None,
        description="A conversation to continue, as a previous answer "
        "returned it. Omit it to start a new one. Continuing a conversation "
        "is what lets a follow-up be answered from what was already "
        "retrieved, without searching again.",
    )

    @field_validator("question")
    @classmethod
    def _reject_empty(cls, value: str) -> str:
        """Reject a question that is empty or only whitespace.

        Args:
            value: The submitted question.

        Returns:
            The question, with surrounding whitespace removed.

        Raises:
            ValueError: If nothing but whitespace was submitted.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped


class CitationModel(BaseModel):
    """One passage an answer was drawn from, as a reader would look it up."""

    chunk_id: int = Field(description="Row id of the chunk in the store.")
    document_slug: str = Field(description="Slug of the document it came from.")
    source_kind: str = Field(
        description="What the document was read out of: transcript, docx, "
        "pptx, or xlsx."
    )
    title: str = Field(description="The document's title, or a meeting's subject.")
    document_date: str = Field(description="The document's date, ISO 8601.")
    author: str | None = Field(
        description="Who wrote it, or null for a transcript, which has "
        "attendees rather than an author."
    )
    location: str = Field(
        description="Where in the document the passage sits: a turn range, "
        "a heading path, a slide number, a sheet and row range."
    )


class AnswerResponse(BaseModel):
    """What ``POST /answer`` returns: prose, and what it rests on."""

    question: str = Field(
        description="The question as it was asked, whitespace trimmed."
    )
    answer: str = Field(
        description="The answer in prose. A statement that the record does "
        "not settle the question is a normal answer, not an error — and a "
        "question outside the corpus is declined here too."
    )
    citations: list[CitationModel] = Field(
        description="The passages retrieved while answering, best first. "
        "Empty when the agent answered without searching, which is what an "
        "out-of-scope question and a follow-up already covered both do."
    )
    searches: int = Field(
        description="How many searches the agent ran for this question. "
        "Zero when it did not search, more than one when the question had "
        "more than one part."
    )
    thread_id: str = Field(
        description="The conversation this answer belongs to. Send it back "
        "to ask a follow-up against the same history."
    )
