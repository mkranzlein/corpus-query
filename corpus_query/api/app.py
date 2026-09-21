"""The query API: retrieval, an agent over it, a health check, and the page.

``POST /search`` takes a natural-language question and returns the corpus
chunks that bear on it, each carrying its provenance and the metadata
enrichment derived from it, alongside the confidence signals the retrieval
pipeline reports. It returns passages, not prose.

``POST /answer`` takes the same kind of question and returns an answer written
out of those passages, with the passages it rests on. It is a caller of
``/search`` rather than a replacement for it: the agent posts to that endpoint
like any other client, so the two can be asked the same question and compared,
and the endpoint that ranks is still curlable on its own.

``GET /`` serves the browser application, built from ``frontend/`` and
committed under ``static/`` beside this module. It is mounted last, so the
JSON endpoints and the generated OpenAPI documents keep their paths and
nothing about them changes by virtue of a page existing.

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

import sqlite3
from collections.abc import Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from chromadb.api.models.Collection import Collection
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from corpus_query.agent.runtime import OpenAgent, open_agent
from corpus_query.api.models import (
    AnswerRequest,
    AnswerResponse,
    CitationModel,
    ConfidenceModel,
    DatabaseHealth,
    HealthResponse,
    IndexHealth,
    SearchRequest,
    SearchResponse,
    SearchResultModel,
)
from corpus_query.retrieval.index import DEFAULT_INDEX_DIR, open_index
from corpus_query.retrieval.search import SearchResult
from corpus_query.retrieval.search import search as run_search
from corpus_query.store.db import DEFAULT_DATABASE_FILE, connect

#: Runs one query against the store and the index. The project's retrieval
#: pipeline by default; overridable so the HTTP layer can be tested without
#: ranking anything.
type SearchFn = Callable[..., SearchResult]

#: Opens everything the service needs, once, at startup.
type OpenResources = Callable[[], "Resources"]

#: The built browser application. Vite writes here and the result is
#: committed, which is what lets a clone run the whole system with Python
#: alone — see the README. Nothing at run time builds it, and nothing at run
#: time needs Node.
DEFAULT_STATIC_DIR = Path(__file__).parent / "static"


class StartupError(RuntimeError):
    """The service cannot serve queries with what it was pointed at."""


@dataclass
class Resources:
    """What the service holds open for its whole lifetime."""

    connection: sqlite3.Connection
    collection: Collection

    def close(self) -> None:
        """Release the document store connection."""
        self.connection.close()


def open_resources(
    database: Path | str = DEFAULT_DATABASE_FILE,
    index_dir: Path | str = DEFAULT_INDEX_DIR,
    warm_models: bool = True,
) -> Resources:
    """Open the store and the index, and load the models.

    Args:
        database: The document store to serve queries against.
        index_dir: Where the vector index lives. Rebuilt from the store's
            embeddings if it is missing or disagrees with them.
        warm_models: Whether to load the embedder and the reranker now.
            False leaves them to load on first use, which is only what a
            test wants.

    Returns:
        The open store and index.

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
        if warm_models:
            _warm_models()
    except BaseException:
        connection.close()
        raise
    return Resources(connection=connection, collection=collection)


def create_app(
    resources: OpenResources | None = None,
    search: SearchFn | None = None,
    agent: OpenAgent | None = None,
    static_dir: Path | str | None = None,
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

    Returns:
        The application, ready to be served.
    """
    open_them = resources if resources is not None else open_resources
    run = search if search is not None else run_search
    open_it = agent if agent is not None else open_agent

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Open everything before the first request, and close it after.

        The agent is opened last and given the application itself, because
        it reaches retrieval by posting to ``/search`` on it. That is a
        cycle only in the object graph: the routes are registered by the
        time the lifespan runs, and no request is served until it yields.
        """
        opened = open_them()
        app.state.resources = opened
        try:
            async with AsyncExitStack() as stack:
                app.state.agent = await stack.enter_async_context(open_it(app))
                yield
        finally:
            opened.close()

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

    @app.post("/answer", response_model=AnswerResponse)
    async def answer_endpoint(payload: AnswerRequest, request: Request):
        """Answer one question out of the corpus.

        The graph was compiled at startup; this awaits it. Whether
        retrieval runs, and how many times, is the agent's decision rather
        than this handler's.

        Args:
            payload: The question, and the conversation to continue if
                there is one.
            request: The live request, for the agent opened at startup.

        Returns:
            The answer, the passages it rests on, and the conversation it
            belongs to. A question the corpus cannot settle comes back as
            an answer saying so, not as an error, and so does one the
            corpus was never going to be asked.
        """
        agent = request.app.state.agent
        result = await agent.answer(payload.question, thread_id=payload.thread_id)
        return AnswerResponse(
            question=payload.question,
            answer=result.answer,
            citations=[CitationModel(**row) for row in result.citations],
            searches=result.searches,
            thread_id=result.thread_id,
        )

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

    Args:
        app: The application to mount onto.
        directory: The built application, as Vite wrote it.
    """
    if directory.is_dir():
        # html=True is what makes ``/`` serve index.html rather than a
        # directory listing.
        app.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
        return

    @app.get("/", response_class=PlainTextResponse)
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
