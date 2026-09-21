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

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from corpus_query.retrieval.search import DEFAULT_RESULTS, Confidence, Result

#: The most results one request may ask for. The cross-encoder scores every
#: fused candidate, so an unbounded limit is an unbounded request.
MAX_RESULTS = 50


def _required(value: str, field: str) -> str:
    """Trim a submitted string and reject one that says nothing.

    Args:
        value: What was submitted.
        field: The field's name, for the message.

    Returns:
        The value, with surrounding whitespace removed.

    Raises:
        ValueError: If nothing but whitespace was submitted.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field} must not be empty")
    return stripped


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
    attendees: list[str] = Field(
        description="Who was in the room, for a transcript. Empty for a "
        "document that names an author."
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
            attendees=list(result.attendees),
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
    attendees: list[str] = Field(
        default_factory=list,
        description="Who was in the room, for a transcript. Empty for a "
        "document that names an author.",
    )
    location: str = Field(
        description="Where in the document the passage sits: a turn range, "
        "a heading path, a slide number, a sheet and row range."
    )


class RoutingCandidateModel(BaseModel):
    """One person worth asking, and the passages that named them."""

    name: str = Field(description="The person, as the roster spells them.")
    role: str = Field(description="Their role, from the roster.")
    department: str = Field(description="Their department, from the roster.")
    passages: int = Field(
        description="How many of the retrieved passages this person wrote "
        "or attended. What the ranking is by."
    )
    evidence: list[CitationModel] = Field(
        description="Those passages, cited the way an answer's claims are "
        "cited, so a suggestion can be followed back to what produced it."
    )


class RoutingModel(BaseModel):
    """Who to ask when the record did not settle the question."""

    candidates: list[RoutingCandidateModel] = Field(
        description="People worth asking, best first."
    )
    question: str = Field(
        description="The user's question restated so it stands on its own, "
        "with the context that made it unanswerable. Text to edit and send, "
        "not something this service sends anywhere."
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
    routing: RoutingModel | None = Field(
        default=None,
        description="Who to ask, when the agent searched and could not "
        "answer from what came back. Null for an answered question and for "
        "an out-of-scope one, which is declined without a search and routes "
        "to nobody.",
    )
    thread_id: str = Field(
        description="The conversation this answer belongs to. Send it back "
        "to ask a follow-up against the same history."
    )
    answer_id: str = Field(
        description="The id of the row recorded for this question. Send it "
        "back with a correction or a piece of feedback to say which answer "
        "is being written about."
    )


class CorrectionRequest(BaseModel):
    """What a user says one answer got wrong, and what is true instead."""

    answer_id: str = Field(
        description="The answer being corrected, as ``POST /answer`` returned it."
    )
    what_was_wrong: str = Field(
        description="What the answer claimed that it should not have.",
        examples=["It said the firmware freeze is March 12th."],
    )
    what_is_right: str = Field(
        description="What is true instead. Both halves are required: a "
        "correction that only says an answer was wrong is feedback.",
        examples=["The freeze moved to March 19th."],
    )

    @field_validator("answer_id", "what_was_wrong", "what_is_right")
    @classmethod
    def _reject_empty(cls, value: str, info) -> str:
        """Reject a field that is empty or only whitespace.

        Args:
            value: The submitted text.
            info: The field being validated, for the message.

        Returns:
            The text, with surrounding whitespace removed.

        Raises:
            ValueError: If nothing but whitespace was submitted.
        """
        return _required(value, info.field_name)


class FeedbackRequest(BaseModel):
    """A verdict on one answer, with an optional note."""

    answer_id: str = Field(
        description="The answer being judged, as ``POST /answer`` returned it."
    )
    verdict: Literal["up", "down"] = Field(
        description='"up" or "down". A bare "down" is a verdict rather than '
        "a correction: it says an answer was bad and carries nothing a "
        "reader can act on."
    )
    note: str | None = Field(
        default=None,
        description="Anything the user wanted to add. Optional, and null "
        "when there was nothing.",
    )

    @field_validator("answer_id")
    @classmethod
    def _reject_empty(cls, value: str) -> str:
        """Reject an answer id that is empty or only whitespace.

        Args:
            value: The submitted id.

        Returns:
            The id, with surrounding whitespace removed.

        Raises:
            ValueError: If nothing but whitespace was submitted.
        """
        return _required(value, "answer_id")

    @field_validator("note")
    @classmethod
    def _blank_is_no_note(cls, value: str | None) -> str | None:
        """Treat a whitespace-only note as no note at all.

        Args:
            value: The submitted note, or None.

        Returns:
            The trimmed note, or None when there was nothing in it.
        """
        if value is None:
            return None
        return value.strip() or None


class RecordModel(BaseModel):
    """What every captured record carries.

    The question and the answer come along on each row rather than being
    left behind an id, so a reader working through gaps or corrections can
    read one without a second call.
    """

    id: int = Field(description="Row id of this record.")
    answer_id: str = Field(description="The answer it was recorded against.")
    created_at: str = Field(description="When it was recorded, ISO 8601, UTC.")
    thread_id: str = Field(
        description="The conversation the answer belongs to, for reading the "
        "exchange around it."
    )
    question: str = Field(description="The question as it was asked.")
    answer: str = Field(description="The answer that was given.")
    abstained: bool = Field(
        description="Whether the record failed to settle that question."
    )
    citations: list[CitationModel] = Field(
        default_factory=list,
        description="The passages the answer rested on, best first. Empty "
        "when it rested on none.",
    )
    reviewed_at: str | None = Field(
        default=None,
        description="When someone reading the review queue marked it seen, "
        "ISO 8601, UTC, or null while it is still new.",
    )


class ReviewRequest(BaseModel):
    """What ``PATCH`` on one gap, correction, or piece of feedback takes."""

    reviewed: bool = Field(
        description="True to mark the record reviewed, false to put it back "
        "among the new ones. Marking one already reviewed keeps the time it "
        "was first marked."
    )


class GapModel(RecordModel):
    """A question the record did not settle, detected rather than reported."""

    routing: RoutingModel | None = Field(
        default=None,
        description="Who to ask, as it was suggested at the time, or null "
        "when the passages named nobody on the roster.",
    )


class CorrectionModel(RecordModel):
    """A user-supplied correction to one answer."""

    what_was_wrong: str = Field(
        description="What the answer claimed that it should not have."
    )
    what_is_right: str = Field(description="What is true instead.")


class FeedbackModel(RecordModel):
    """A verdict on one answer."""

    verdict: str = Field(description='"up" or "down".')
    note: str | None = Field(description="What the user added, or null.")


class GapsResponse(BaseModel):
    """What ``GET /gaps`` returns."""

    gaps: list[GapModel] = Field(
        description="Gaps, most recent first. Empty when none were recorded."
    )


class CorrectionsResponse(BaseModel):
    """What ``GET /corrections`` returns."""

    corrections: list[CorrectionModel] = Field(
        description="Corrections, most recent first. Empty when none were recorded."
    )


class FeedbackResponse(BaseModel):
    """What ``GET /feedback`` returns."""

    feedback: list[FeedbackModel] = Field(
        description="Verdicts, most recent first. Empty when none were recorded."
    )
