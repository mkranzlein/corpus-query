"""The query API: retrieval, an agent over it, a health check, and the page.

``POST /search`` takes a natural-language question and returns the corpus
chunks that bear on it, each carrying its provenance and the metadata
enrichment derived from it, alongside the confidence signals the retrieval
pipeline reports. It returns passages, not prose.

``POST /answer`` takes the same kind of question and returns an answer written
out of those passages, with the passages it rests on. It is a caller of
``/search`` rather than a replacement for it: the agent posts to that endpoint
like any other client, so the two can be asked the same question and compared,
and the endpoint that ranks is still curlable on its own. A client that asks
for ``text/event-stream`` gets the same answer as server-sent events, preceded
by one event per step the agent takes, since a local model can take tens of
seconds and a page that shows nothing for that long reads as broken. Anything
else gets one JSON body.

``GET /chunks/{chunk_id}`` reads one passage back by the id a citation
carries: its text, and the topics, time sensitivity, and business impact
derived for its document, none of which a citation holds.

``POST /corrections`` and ``POST /feedback`` record what an answer got
wrong, against the id ``/answer`` returned, and ``GET /gaps``,
``GET /corrections``, and ``GET /feedback`` read the three kinds back, most
recent first. A gap needs no endpoint to be written: the service records one
itself whenever the record did not settle a question. Nor does a correction
typed into the conversation: sent to ``/answer`` as the next message, it is
recorded by the agent against the earlier answer it corrects, in the same
table ``POST /corrections`` writes to, and comes back on that response's
``correction`` field. ``GET`` on
``/gaps/{id}``, ``/corrections/{id}``, or ``/feedback/{id}`` reads one record,
and ``PATCH`` on the same path marks it reviewed or clears the mark — the one
change a record takes after it is written. All of it goes in the usage
database, which is the local uncommitted file beside the corpus — using the
system never modifies a file under version control.

``GET /`` serves the browser application, built from ``frontend/`` and
committed under ``static/`` beside this module. It is mounted last, so the
JSON endpoints and the generated OpenAPI documents keep their paths and
nothing about them changes by virtue of a page existing. ``GET /review``
serves the same page, which shows the review queue when that is the path it
was loaded at; nothing on the question-and-answer page links there.

Everything expensive happens once, at startup: the document store is opened,
the vector index is opened — rebuilt from the embeddings already in the store
if it is missing or stale — and the embedding and reranking models are loaded
into memory. A request that pays for a model load is the difference between an
API that is fast and one that looks broken, so none of that is deferred to the
first query. Building the index is deliberately not a command a user runs;
:func:`corpus_query.retrieval.index.open_index` already knows when the index
disagrees with the store, and an index that is a cache of committed data is a
poor thing to make someone remember.

Startup is also where a missing corpus is caught. A store that is not there,
or one holding no chunks, fails loudly before the socket is listening, rather
than leaving a service that answers every question with no results and no
explanation.

Requests are handled on the event loop thread rather than in a worker
threadpool, because a SQLite connection belongs to the thread that opened it
and this one is opened during startup. Queries are therefore served one at a
time. That is the right trade for a local service over one corpus; a version
that needs concurrency wants a connection per request, which is a change to
make when something asks for it.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chromadb.api.models.Collection import Collection
from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.sse import EventSourceResponse, format_sse_event
from fastapi.staticfiles import StaticFiles

from corpus_query import tracing
from corpus_query.agent.graph import EVENTS, Agent, Answer
from corpus_query.agent.runtime import OpenAgent, open_agent
from corpus_query.api.models import (
    AnswerRequest,
    AnswerResponse,
    ChunkModel,
    CitationModel,
    ConfidenceModel,
    CorrectionModel,
    CorrectionRequest,
    CorrectionsResponse,
    DatabaseHealth,
    FeedbackModel,
    FeedbackRequest,
    FeedbackResponse,
    GapModel,
    GapsResponse,
    HealthResponse,
    IndexHealth,
    RecordModel,
    ReviewRequest,
    RoutingModel,
    SearchRequest,
    SearchResponse,
    SearchResultModel,
)
from corpus_query.retrieval.index import DEFAULT_INDEX_DIR, open_index
from corpus_query.retrieval.search import SearchResult, read_chunk
from corpus_query.retrieval.search import search as run_search
from corpus_query.store import capture
from corpus_query.store.capture import (
    DEFAULT_RECORDS,
    MAX_RECORDS,
    UnknownAnswerError,
    UnknownRecordError,
)
from corpus_query.store.db import DEFAULT_DATABASE_FILE, connect

#: Runs one query against the store and the index. The project's retrieval
#: pipeline by default; overridable so the HTTP layer can be tested without
#: ranking anything.
type SearchFn = Callable[..., SearchResult]

#: Opens everything the service needs, once, at startup.
type OpenResources = Callable[[], "Resources"]

#: Starts recording spans, once, at startup.
type OpenTracing = Callable[[], tracing.Tracing]

#: The built browser application. Vite writes here and the result is
#: committed, which is what lets a clone run the whole system with Python
#: alone — see the README. Nothing at run time builds it, and nothing at run
#: time needs Node.
DEFAULT_STATIC_DIR = Path(__file__).parent / "static"

#: The media type a client asks for, in ``Accept``, to have ``/answer``
#: stream its progress instead of returning one JSON body.
EVENT_STREAM = "text/event-stream"

logger = logging.getLogger(__name__)


class StartupError(RuntimeError):
    """The service cannot serve queries with what it was pointed at."""


@dataclass
class Resources:
    """What the service holds open for its whole lifetime."""

    connection: sqlite3.Connection
    """The document store. Read to answer questions and never written to."""

    collection: Collection

    captured: sqlite3.Connection
    """The usage database, where what the system got wrong is recorded. A
    second file, opened here for the same reason the first one is: a
    connection belongs to the thread that opened it, and requests are served
    on the thread that ran startup."""

    def close(self) -> None:
        """Release both connections."""
        self.connection.close()
        self.captured.close()


def open_resources(
    database: Path | str = DEFAULT_DATABASE_FILE,
    index_dir: Path | str = DEFAULT_INDEX_DIR,
    warm_models: bool = True,
    usage_database: Path | str | None = None,
) -> Resources:
    """Open the stores and the index, and load the models.

    Args:
        database: The document store to serve queries against.
        index_dir: Where the vector index lives. Rebuilt from the store's
            embeddings if it is missing or disagrees with them.
        warm_models: Whether to load the embedder and the reranker now.
            False leaves them to load on first use, which is only what a
            test wants.
        usage_database: Where to record what the system got wrong. Created,
            with its directory, if it is not there yet. None resolves to the
            project's default when the service starts.

    Returns:
        The open stores and index.

    Raises:
        StartupError: If the store is missing, unreadable, or holds no
            chunks to search.
    """
    path = Path(database)
    if not path.exists():
        raise StartupError(
            f"no document store at {path}. Ingest a corpus first: "
            f"uv run scripts/ingest.py"
        )
    try:
        connection = connect(path)
        (chunks,) = connection.execute("SELECT count(*) FROM chunks").fetchone()
    except sqlite3.Error as exc:
        raise StartupError(f"cannot read the document store at {path}: {exc}") from exc
    # Anything that goes wrong from here on leaves the service refusing to
    # start, so the connection is closed on the way out rather than left to
    # the garbage collector.
    try:
        if not chunks:
            raise StartupError(
                f"the document store at {path} holds no chunks. Ingest a "
                f"corpus first: uv run scripts/ingest.py"
            )
        collection = open_index(connection, index_dir)
        captured = capture.connect(usage_database)
        try:
            if warm_models:
                _warm_models()
        except BaseException:
            captured.close()
            raise
    except BaseException:
        connection.close()
        raise
    return Resources(connection=connection, collection=collection, captured=captured)


def create_app(
    resources: OpenResources | None = None,
    search: SearchFn | None = None,
    agent: OpenAgent | None = None,
    static_dir: Path | str | None = None,
    traces: OpenTracing | None = None,
) -> FastAPI:
    """Build the application.

    Args:
        resources: What to open at startup. Defaults to
            :func:`open_resources` against the project's usual paths.
            Overridable so a test can supply a store and an index it built
            itself.
        search: What to run a query with. Defaults to the project's
            retrieval pipeline. Overridable so the HTTP layer can be tested
            without ranking anything.
        agent: What to answer with, as a context manager over the
            application's lifetime. Defaults to
            :func:`corpus_query.agent.runtime.open_agent`, which compiles
            the graph against the project's local model. Overridable so a
            test can drive the graph without a model behind it.
        static_dir: The built browser application to serve at ``/``.
            Defaults to :data:`DEFAULT_STATIC_DIR`, the bundle committed
            beside this module.
        traces: What to start recording spans with. Defaults to
            :func:`corpus_query.tracing.open_tracing` against the project's
            usage database, which reads from the environment whether
            tracing is on and where else spans go.

    Returns:
        The application, ready to be served.
    """
    open_them = resources if resources is not None else open_resources
    run = search if search is not None else run_search
    open_it = agent if agent is not None else open_agent
    open_traces = traces if traces is not None else tracing.open_tracing

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Open everything before the first request, and close it after.

        The agent is opened last and given the application itself, because
        it reaches retrieval by posting to ``/search`` on it. That is a
        cycle only in the object graph: the routes are registered by the
        time the lifespan runs, and no request is served until it yields.

        Tracing is started first and stopped last, so every span a request
        opens has somewhere to go, and the spans still queued when the
        service stops are written once the agent's connection to the same
        file has closed.
        """
        recording = open_traces()
        try:
            opened = open_them()
            app.state.resources = opened
            try:
                async with AsyncExitStack() as stack:
                    app.state.agent = await stack.enter_async_context(open_it(app))
                    yield
            finally:
                opened.close()
        finally:
            await recording.aclose()

    app = FastAPI(
        title="corpus-query",
        summary="Ask a corpus of meeting transcripts a question, and get "
        "back the passages that bear on it.",
        lifespan=lifespan,
    )

    @app.post("/search", response_model=SearchResponse)
    async def search_endpoint(payload: SearchRequest, request: Request):
        """Rank the corpus against one question.

        Args:
            payload: The query and how many results to return.
            request: The live request, for the resources opened at startup.

        Returns:
            The ranked results and the confidence signals about them. A
            query that matches nothing is an answer, so it comes back as an
            empty result list rather than an error.
        """
        opened: Resources = request.app.state.resources
        # The agent's search tool sends its trace along with the request, so
        # the retrieval spans below belong to the answer that asked for them.
        with tracing.continued(request.headers):
            result = run(
                opened.connection,
                opened.collection,
                payload.query,
                results=payload.limit,
            )
        return SearchResponse(
            query=payload.query,
            results=[SearchResultModel.from_result(row) for row in result.results],
            confidence=ConfidenceModel.from_confidence(result.confidence),
        )

    @app.get(
        "/chunks/{chunk_id}",
        response_model=ChunkModel,
        responses={404: {"description": "No chunk has that id."}},
    )
    async def chunk_endpoint(chunk_id: int, request: Request):
        """Read one passage by id, with its text and derived metadata.

        An answer's citations say where each passage came from but not what
        it says, so a reader opening one reads it here. This reads the
        corpus and nothing else, and ranks nothing.

        Args:
            chunk_id: The passage, as a citation or a search result names it.
            request: The live request, for the store opened at startup.

        Returns:
            The passage's text, where it sits, who wrote it or was in the
            room, and the topics, time sensitivity, and business impact
            derived for its document.

        Raises:
            HTTPException: 404, if the corpus holds no chunk with that id.
        """
        opened: Resources = request.app.state.resources
        chunk = read_chunk(opened.connection, chunk_id)
        if chunk is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no chunk with id {chunk_id}",
            )
        return ChunkModel.from_chunk(chunk_id, chunk)

    @app.post(
        "/answer",
        response_model=AnswerResponse,
        responses={
            200: {
                "description": "One JSON body by default. With ``Accept: "
                "text/event-stream``, server-sent events instead: "
                + "; ".join(
                    f"``{name}``: {meaning}" for name, meaning in EVENTS.items()
                )
                + "; ``answer``: the finished answer, the same JSON body a "
                "request without the header gets; ``error``: the run failed "
                "partway, and ``detail`` says why. The stream ends after "
                "``answer`` or ``error``.",
                "content": {EVENT_STREAM: {"schema": {"type": "string"}}},
            }
        },
    )
    async def answer_endpoint(payload: AnswerRequest, request: Request):
        """Answer one question out of the corpus.

        The graph was compiled at startup; this awaits it. Whether
        retrieval runs, and how many times, is the agent's decision rather
        than this handler's.

        A client that sends ``Accept: text/event-stream`` gets the same run
        as server-sent events: one as each step starts or reports what it
        found, and the finished answer last, in the same shape this returns
        otherwise. Anything else gets the one JSON body, so ``curl`` with no
        headers is unaffected.

        Args:
            payload: The question, and the conversation to continue if
                there is one.
            request: The live request, for the agent opened at startup.

        Returns:
            The answer, the passages it rests on, and the conversation it
            belongs to. A question the corpus cannot settle comes back as
            an answer saying so, not as an error, and so does one the
            corpus was never going to be asked. The first of those two also
            comes back with a suggestion of who to ask; the second routes
            to nobody.
        """
        opened: Resources = request.app.state.resources
        agent = request.app.state.agent
        if _wants_events(request):
            return EventSourceResponse(
                _answer_events(agent, opened, payload),
                # Nothing in between should hold events back to batch them,
                # which is the whole of what streaming them is for.
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        result = await agent.answer(payload.question, thread_id=payload.thread_id)
        return _recorded(opened, payload.question, result)

    @app.post(
        "/corrections",
        response_model=CorrectionModel,
        status_code=status.HTTP_201_CREATED,
    )
    async def record_correction_endpoint(payload: CorrectionRequest, request: Request):
        """Record what an answer got wrong, and what is right.

        Args:
            payload: The answer being corrected, and both halves of the
                correction.
            request: The live request, for the resources opened at startup.

        Returns:
            The correction as a read of it would return it.

        Raises:
            HTTPException: 404 if no answer has that id.
        """
        opened: Resources = request.app.state.resources
        try:
            written = capture.record_correction(
                opened.captured,
                payload.answer_id,
                what_was_wrong=payload.what_was_wrong,
                what_is_right=payload.what_is_right,
            )
        except UnknownAnswerError as exc:
            raise _unknown_answer(exc) from exc
        return CorrectionModel(**written)

    @app.post(
        "/feedback",
        response_model=FeedbackModel,
        status_code=status.HTTP_201_CREATED,
    )
    async def record_feedback_endpoint(payload: FeedbackRequest, request: Request):
        """Record a verdict on an answer.

        Args:
            payload: The answer being judged, the verdict, and any note.
            request: The live request, for the resources opened at startup.

        Returns:
            The verdict as a read of it would return it.

        Raises:
            HTTPException: 404 if no answer has that id.
        """
        opened: Resources = request.app.state.resources
        try:
            written = capture.record_feedback(
                opened.captured,
                payload.answer_id,
                verdict=payload.verdict,
                note=payload.note,
            )
        except UnknownAnswerError as exc:
            raise _unknown_answer(exc) from exc
        return FeedbackModel(**written)

    @app.get("/gaps", response_model=GapsResponse)
    async def gaps_endpoint(request: Request, limit: int = _limit()):
        """Read back the questions the record did not settle.

        Args:
            request: The live request, for the resources opened at startup.
            limit: How many to return at most.

        Returns:
            Gaps, most recent first, each with the question that produced
            it, the answer that was given, and the suggestion made at the
            time.
        """
        opened: Resources = request.app.state.resources
        rows = capture.gaps(opened.captured, limit=limit)
        return GapsResponse(gaps=[GapModel(**row) for row in rows])

    @app.get("/corrections", response_model=CorrectionsResponse)
    async def corrections_endpoint(request: Request, limit: int = _limit()):
        """Read back what users said the answers got wrong.

        Args:
            request: The live request, for the resources opened at startup.
            limit: How many to return at most.

        Returns:
            Corrections, most recent first, each with the question and
            answer it was written against.
        """
        opened: Resources = request.app.state.resources
        rows = capture.corrections(opened.captured, limit=limit)
        return CorrectionsResponse(corrections=[CorrectionModel(**row) for row in rows])

    @app.get("/feedback", response_model=FeedbackResponse)
    async def feedback_endpoint(request: Request, limit: int = _limit()):
        """Read back the verdicts users gave.

        Args:
            request: The live request, for the resources opened at startup.
            limit: How many to return at most.

        Returns:
            Verdicts, most recent first, each with the question and answer
            it was given on.
        """
        opened: Resources = request.app.state.resources
        rows = capture.feedback(opened.captured, limit=limit)
        return FeedbackResponse(feedback=[FeedbackModel(**row) for row in rows])

    _add_record_routes(app, "gaps", GapModel, "gap")
    _add_record_routes(app, "corrections", CorrectionModel, "correction")
    _add_record_routes(app, "feedback", FeedbackModel, "piece of feedback")

    @app.get("/health", response_model=HealthResponse)
    async def health_endpoint(request: Request, response: Response):
        """Report that the app is up and what it is serving from.

        Reaching this at all says the application is running. What it
        answers with says whether the store still reads and whether the
        vector index is loaded, each with what it holds, so a caller can
        tell an empty corpus from a broken one.

        Args:
            request: The live request, for the resources opened at startup.
            response: The outgoing response, whose status is set to 503 if
                either dependency stopped answering.

        Returns:
            The state of the store and the index.
        """
        opened: Resources = request.app.state.resources
        try:
            (chunks,) = opened.connection.execute(
                "SELECT count(*) FROM chunks"
            ).fetchone()
            database = DatabaseHealth(readable=True, chunks=chunks)
        except sqlite3.Error:
            database = DatabaseHealth(readable=False)
        try:
            index = IndexHealth(loaded=True, vectors=opened.collection.count())
        except Exception:
            index = IndexHealth(loaded=False)

        healthy = database.readable and index.loaded
        if not healthy:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="ok" if healthy else "degraded", database=database, index=index
        )

    _mount_frontend(app, DEFAULT_STATIC_DIR if static_dir is None else Path(static_dir))
    return app


def _wants_events(request: Request) -> bool:
    """Return whether a request asked for its answer as an event stream.

    Args:
        request: The live request.

    Returns:
        True when ``Accept`` names ``text/event-stream``. A wildcard does
        not count: ``curl`` sends ``*/*``, and it gets the JSON it always
        has.
    """
    accepted = request.headers.get("accept", "")
    return any(
        part.split(";", 1)[0].strip().lower() == EVENT_STREAM
        for part in accepted.split(",")
    )


def _recorded(opened: Resources, question: str, result: Answer) -> AnswerResponse:
    """Record one answer, and the gap it leaves if it left one.

    Both ways of asking — one JSON body and a stream of events — record
    through here, so every question answered writes one row, with the same
    per-query numbers, an abstention included.

    Args:
        opened: The resources opened at startup, for the usage database.
        question: The question as it was asked.
        result: What the agent answered.

    Returns:
        The response body, carrying the id the answer was recorded under.
    """
    answer_id = capture.record_answer(
        opened.captured,
        query=question,
        answer=result.answer,
        citations=result.citations,
        thread_id=result.thread_id,
        abstained=result.abstained,
        answer_id=result.answer_id or None,
        searches=result.searches,
        top_score=result.top_score,
        margin=result.margin,
        citation_coverage=result.citation_coverage,
        latency_ms=result.latency_ms,
        backend=result.backend,
        model=result.model,
        trace_id=result.trace_id,
    )
    # A gap is written by the system rather than reported by anybody, so
    # this is the only place it can come from. The suggestion is stored as
    # it was made, since the roster and the corpus both move on.
    if result.abstained or result.routing is not None:
        capture.record_gap(opened.captured, answer_id, routing=result.routing)
    return AnswerResponse(
        question=question,
        answer=result.answer,
        citations=[CitationModel(**row) for row in result.citations],
        searches=result.searches,
        abstained=result.abstained,
        routing=(
            RoutingModel(**result.routing) if result.routing is not None else None
        ),
        thread_id=result.thread_id,
        answer_id=answer_id,
        correction=(
            CorrectionModel(**result.correction)
            if result.correction is not None
            else None
        ),
    )


async def _answer_events(
    agent: Agent, opened: Resources, payload: AnswerRequest
) -> AsyncIterator[bytes]:
    """Run one question, as server-sent events.

    The response has already started by the time the first event is sent,
    so a failure partway cannot become a status code. It becomes an
    ``error`` event instead, and the stream ends there, rather than the
    connection simply closing and leaving the client to guess whether the
    answer was finished. The traceback goes to the service's log, as it
    does for a request that fails before responding.

    A client that stops listening is not caught here. The server cancels
    the response, the cancellation stops the graph at whatever it was
    awaiting, and nothing is recorded, since nothing was answered. The
    half-finished turn left on the thread is cleared by the next question
    asked on it; see :meth:`corpus_query.agent.graph.Agent.stream`.

    Args:
        agent: The agent opened at startup.
        opened: The resources opened at startup, for the usage database.
        payload: The question, and the conversation to continue.

    Yields:
        One encoded event per step, then ``answer`` or ``error``.
    """
    try:
        async for item in agent.stream(payload.question, thread_id=payload.thread_id):
            if isinstance(item, Answer):
                body = _recorded(opened, payload.question, item)
                yield _event("answer", body.model_dump(mode="json"))
            else:
                yield _event(item.event, item.data)
    except Exception as exc:
        logger.exception("answering failed partway through a stream")
        yield _event("error", {"detail": f"{type(exc).__name__}: {exc}"})


def _event(name: str, data: dict[str, Any]) -> bytes:
    """Encode one server-sent event.

    Args:
        name: The event type, which a browser dispatches on.
        data: Its payload, sent as JSON.

    Returns:
        The event on the wire.
    """
    return format_sse_event(event=name, data_str=json.dumps(data))


def _limit() -> Any:
    """Build the ``limit`` parameter the three reads share.

    Returns:
        The query parameter, bounded. These reads are for a person catching
        up on what the system got wrong, so an unbounded one would be a
        table export behind a page of prose.
    """
    return Query(default=DEFAULT_RECORDS, ge=1, le=MAX_RECORDS)


def _add_record_routes(
    app: FastAPI, kind: str, model: type[RecordModel], noun: str
) -> None:
    """Add reading one record, and marking it reviewed, for one kind.

    The three kinds are read and marked identically, so the two routes are
    written once and added three times rather than copied.

    Args:
        app: The application to add them to.
        kind: The kind, one of :data:`corpus_query.store.capture.KINDS`,
            which is also the path the list of that kind is served at.
        model: What one record of that kind is returned as.
        noun: What one record of that kind is called, for the generated
            documentation.
    """

    async def read_endpoint(record_id: int, request: Request):
        """Read one record of this kind by its id."""
        opened: Resources = request.app.state.resources
        try:
            row = capture.record(opened.captured, kind, record_id)
        except UnknownRecordError as exc:
            raise _unknown_record(exc) from exc
        return model(**row)

    async def review_endpoint(record_id: int, payload: ReviewRequest, request: Request):
        """Mark one record of this kind reviewed, or clear the mark."""
        opened: Resources = request.app.state.resources
        try:
            row = capture.mark_reviewed(
                opened.captured, kind, record_id, reviewed=payload.reviewed
            )
        except UnknownRecordError as exc:
            raise _unknown_record(exc) from exc
        return model(**row)

    app.add_api_route(
        f"/{kind}/{{record_id}}",
        read_endpoint,
        methods=["GET"],
        response_model=model,
        summary=f"Read one {noun}",
        description=f"One {noun}, with the question, answer, and citations "
        f"it was recorded against. 404 if no {noun} has that id.",
        operation_id=f"read_{kind}_record",
    )
    app.add_api_route(
        f"/{kind}/{{record_id}}",
        review_endpoint,
        methods=["PATCH"],
        response_model=model,
        summary=f"Mark one {noun} reviewed, or clear the mark",
        description=f"Sets whether the {noun} has been seen by someone "
        f"reading the review queue. Nothing else about it changes. 404 if "
        f"no {noun} has that id.",
        operation_id=f"review_{kind}_record",
    )


def _unknown_record(exc: UnknownRecordError) -> HTTPException:
    """Turn an unknown record id into the status that says so.

    Args:
        exc: What the store raised.

    Returns:
        The 404 to raise in its place.
    """
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _unknown_answer(exc: UnknownAnswerError) -> HTTPException:
    """Turn an unknown answer id into the status that says so.

    A record pointing at an answer that does not exist is a caller naming
    the wrong thing, not a server fault, and it is refused rather than
    stored as an orphan nothing could read back.

    Args:
        exc: What the store raised.

    Returns:
        The 404 to raise in its place.
    """
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _mount_frontend(app: FastAPI, directory: Path) -> None:
    """Serve the built browser application at ``/``.

    The mount goes on after every endpoint above it. Starlette matches
    routes in the order they were added and a mount at ``/`` matches
    everything, so anything registered afterwards would never be reached —
    which is exactly why this is the last thing ``create_app`` does.

    A missing directory is not a failure to start. The bundle is committed,
    so it is there in any clone; the one way to be without it is to have
    deleted it or to be running from somewhere it was never checked out,
    and the JSON endpoints work perfectly well either way. That case gets a
    page saying how to build it rather than a service that refuses to come
    up over a file nothing else needs.

    ``/review`` is the same page. The application reads the path it was
    loaded at to decide which view to show, so the review queue has an
    address of its own without a second bundle or a client-side router.
    Only that one path is served: a static mount would 404 it, because no
    file is called ``review``, and a catch-all that answered every unknown
    path with the page would turn a mistyped endpoint into a 200.

    ``/review/`` redirects to ``/review`` rather than serving the page
    itself. The bundle's asset URLs are relative, so from ``/review/`` the
    page would ask for ``/review/assets/…`` and load without its script or
    its styles. The redirect puts the browser on the address where they
    resolve. It is registered first because the mount at ``/`` would
    otherwise answer the path with a 404 before FastAPI's own trailing
    slash redirect ever saw it.

    Args:
        app: The application to mount onto.
        directory: The built application, as Vite wrote it.
    """

    @app.get("/review/", include_in_schema=False)
    async def review_with_a_slash() -> RedirectResponse:
        """Send a trailing slash to the address the page's assets resolve from."""
        return RedirectResponse(
            "/review", status_code=status.HTTP_308_PERMANENT_REDIRECT
        )

    if directory.is_dir():
        page = directory / "index.html"

        @app.get("/review", include_in_schema=False)
        async def review_page() -> FileResponse:
            """Serve the application, which shows the review queue here."""
            return FileResponse(page)

        # html=True is what makes ``/`` serve index.html rather than a
        # directory listing.
        app.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
        return

    @app.get("/", response_class=PlainTextResponse)
    @app.get("/review", response_class=PlainTextResponse, include_in_schema=False)
    async def missing_frontend(response: Response) -> str:
        """Say where the page went, and how to put it back."""
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return (
            f"the built frontend is not at {directory}. Build it with "
            f"`npm --prefix frontend ci && npm --prefix frontend run build`, "
            f"or restore it from version control. The /search, /answer, and "
            f"/health endpoints do not need it."
        )


def _warm_models() -> None:
    """Load the embedder and the reranker into memory.

    Both loaders are cached, so loading them here is what makes the first
    query cost no more than the tenth. Imported inside the function because
    importing either module pulls in torch, which is an optional extra — the
    same pattern :mod:`corpus_query.retrieval.dense` and
    :mod:`corpus_query.retrieval.search` use.

    Raises:
        StartupError: If the models extra is not installed. Searching
            without it is not possible, so it is reported here with the
            command that fixes it rather than as an import traceback out of
            a startup hook.
    """
    try:
        from corpus_query.models.embedder import load_embedder
        from corpus_query.models.reranker import load_reranker
    except ImportError as exc:
        raise StartupError(
            f"the embedding and reranking models are not installed ({exc}). "
            f"Run `uv sync --extra models` and try again."
        ) from exc

    load_embedder()
    load_reranker()
