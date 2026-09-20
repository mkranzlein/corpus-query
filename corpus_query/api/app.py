"""The query API: one endpoint over hybrid retrieval, and a health check.

``POST /search`` takes a natural-language question and returns the transcript
chunks that bear on it, each carrying its provenance and the metadata
enrichment derived from it, alongside the confidence signals the retrieval
pipeline reports. It returns passages, not prose — synthesizing an answer out
of them is a later exercise's job, and that agent is a caller of this endpoint
rather than a replacement for it.

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
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from chromadb.api.models.Collection import Collection
from fastapi import FastAPI, Request, Response, status

from corpus_query.api.models import (
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
    resources: OpenResources | None = None, search: SearchFn | None = None
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

    Returns:
        The application, ready to be served.
    """
    open_them = resources if resources is not None else open_resources
    run = search if search is not None else run_search

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Open everything before the first request, and close it after."""
        opened = open_them()
        app.state.resources = opened
        try:
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

    return app


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
