"""Tests for the query API.

These drive the real application in process, over ASGI, with no socket and no
server: httpx speaks to it through :class:`~httpx.ASGITransport`, so status
codes, validation errors, and JSON bodies are the genuine article rather than
a function's return value inspected directly.

Retrieval is stubbed throughout. What ranks above what is settled in the
retrieval tests; what is under test here is the HTTP layer — shapes, status
codes, and what happens when the input or the corpus is not what was hoped
for. Nothing here loads a model, so none of it needs the models extra.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from corpus_query.api.app import (
    Resources,
    StartupError,
    create_app,
    open_resources,
)
from corpus_query.retrieval.search import Confidence, Result, SearchResult
from corpus_query.store.db import connect
from corpus_query.store.kinds import TRANSCRIPT


def request(app, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Make one request against an application, startup and shutdown included.

    Args:
        app: The application to drive.
        method: The HTTP method.
        url: The path to request.
        **kwargs: Passed through to httpx, such as ``json``.

    Returns:
        The response, as any HTTP client would see it.
    """

    async def run() -> httpx.Response:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://api.test"
            ) as client:
                return await client.request(method, url, **kwargs)

    return asyncio.run(run())


class FakeCollection:
    """Stands in for the Chroma collection, counting and nothing else."""

    def __init__(self, count: int = 3, fails: bool = False) -> None:
        self._count = count
        self._fails = fails

    def count(self) -> int:
        """Return how many vectors the index holds.

        Raises:
            RuntimeError: If this fake was built to fail, standing in for an
                index that stopped answering.
        """
        if self._fails:
            raise RuntimeError("index is gone")
        return self._count


@dataclass
class StubSearch:
    """A retrieval pipeline that returns what it was told to, and records."""

    result: SearchResult
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, connection, collection, query, **kwargs) -> SearchResult:
        """Record the call and answer with the canned result."""
        self.calls.append({"query": query, **kwargs})
        return self.result


def a_result(rank: int = 1, chunk_id: int = 7, score: float = 4.5) -> Result:
    """Build one ranked result with every field populated."""
    return Result(
        chunk_id=chunk_id,
        text="Marcus: Two weeks out, assuming the connectors land.",
        document_slug="rev-b-schedule",
        source_kind=TRANSCRIPT,
        title="Rev B schedule",
        document_date="2026-03-04",
        author=None,
        location="turns 0-1",
        span_start=0,
        span_end=1,
        topics=["Hardware", "Supply chain"],
        time_sensitivity="near_term",
        business_impact="moderate",
        rerank_score=score,
        rank=rank,
    )


def a_confidence(**overrides: Any) -> Confidence:
    """Build confidence signals, with fields overridden."""
    return Confidence(
        **{
            "top_score": 4.5,
            "margin": 1.25,
            "lexical_dense_agree": True,
            "unmatched_terms": [],
        }
        | overrides
    )


@pytest.fixture
def app_factory(store):
    """Return a factory for an app over a stubbed pipeline and index."""

    def factory(
        results: list[Result] | None = None,
        confidence: Confidence | None = None,
        collection: FakeCollection | None = None,
    ):
        stub = StubSearch(
            SearchResult(
                results=[a_result()] if results is None else results,
                confidence=a_confidence() if confidence is None else confidence,
            )
        )
        resources = Resources(
            connection=store, collection=collection or FakeCollection()
        )
        app = create_app(resources=lambda: resources, search=stub)
        return app, stub

    return factory


def test_search_returns_ranked_results_with_provenance(app_factory):
    """A result carries its text, where it came from, and what was derived."""
    app, _ = app_factory()

    response = request(app, "POST", "/search", json={"query": "connector lead time"})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "connector lead time"
    [result] = body["results"]
    assert result["rank"] == 1
    assert result["chunk_id"] == 7
    assert result["text"].startswith("Marcus:")
    assert result["document_slug"] == "rev-b-schedule"
    assert result["source_kind"] == TRANSCRIPT
    assert result["title"] == "Rev B schedule"
    assert result["document_date"] == "2026-03-04"
    assert result["author"] is None
    assert result["location"] == "turns 0-1"
    assert (result["span_start"], result["span_end"]) == (0, 1)
    assert result["topics"] == ["Hardware", "Supply chain"]
    assert result["time_sensitivity"] == "near_term"
    assert result["business_impact"] == "moderate"
    assert result["rerank_score"] == 4.5


def test_search_returns_the_confidence_signals(app_factory):
    """The signals the pipeline reports come back alongside the results."""
    app, _ = app_factory(
        confidence=a_confidence(
            margin=None, lexical_dense_agree=False, unmatched_terms=["connecter"]
        )
    )

    body = request(app, "POST", "/search", json={"query": "connecter"}).json()

    assert body["confidence"] == {
        "top_score": 4.5,
        "margin": None,
        "lexical_dense_agree": False,
        "unmatched_terms": ["connecter"],
    }


def test_search_passes_the_limit_through(app_factory):
    """An explicit limit reaches the pipeline; the default is not made up."""
    app, stub = app_factory()

    request(app, "POST", "/search", json={"query": "anything", "limit": 3})

    assert stub.calls == [{"query": "anything", "results": 3}]


def test_search_defaults_the_limit(app_factory):
    """A request without a limit still asks the pipeline for a fixed number."""
    app, stub = app_factory()

    request(app, "POST", "/search", json={"query": "anything"})

    [call] = stub.calls
    assert call["results"] >= 1


def test_search_trims_the_query(app_factory):
    """Surrounding whitespace is not part of the question."""
    app, stub = app_factory()

    body = request(app, "POST", "/search", json={"query": "  connectors\n"}).json()

    assert stub.calls == [{"query": "connectors", "results": 5}]
    assert body["query"] == "connectors"


def test_nothing_matching_is_a_200_with_no_results(app_factory):
    """An empty result set is an answer, not a missing resource."""
    app, _ = app_factory(
        results=[],
        confidence=a_confidence(top_score=None, margin=None, unmatched_terms=["xyzzy"]),
    )

    response = request(app, "POST", "/search", json={"query": "xyzzy"})

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["confidence"]["top_score"] is None
    assert body["confidence"]["unmatched_terms"] == ["xyzzy"]


@pytest.mark.parametrize("payload", [{}, {"limit": 3}])
def test_a_missing_query_is_a_422(app_factory, payload):
    """Leaving the query out names the field that is missing."""
    app, stub = app_factory()

    response = request(app, "POST", "/search", json=payload)

    assert response.status_code == 422
    assert "query" in str(response.json()["detail"])
    assert stub.calls == []


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_an_empty_query_is_a_422_naming_the_problem(app_factory, query):
    """A blank query says so rather than ranking the corpus against nothing."""
    app, stub = app_factory()

    response = request(app, "POST", "/search", json={"query": query})

    assert response.status_code == 422
    assert "query must not be empty" in str(response.json()["detail"])
    assert stub.calls == []


@pytest.mark.parametrize("limit", [0, -1, 500])
def test_an_out_of_range_limit_is_a_422(app_factory, limit):
    """The reranker scores every candidate, so the limit is bounded."""
    app, _ = app_factory()

    response = request(app, "POST", "/search", json={"query": "x", "limit": limit})

    assert response.status_code == 422


def test_health_reports_the_store_and_the_index(app_factory, ingest, store):
    """A healthy service says what it is serving from, with counts."""
    ingest(store, "rev-b-schedule")
    app, _ = app_factory(collection=FakeCollection(count=2))

    response = request(app, "GET", "/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["readable"] is True
    assert body["database"]["chunks"] >= 1
    assert body["index"] == {"loaded": True, "vectors": 2}


def test_health_degrades_when_the_index_stops_answering(app_factory):
    """An index that has gone away is reported, not hidden behind a 200."""
    app, _ = app_factory(collection=FakeCollection(fails=True))

    response = request(app, "GET", "/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["index"] == {"loaded": False, "vectors": None}


def test_health_degrades_when_the_store_stops_answering(app_factory, store):
    """A closed connection is a degraded service, not a crash."""
    app, _ = app_factory()
    store.close()

    response = request(app, "GET", "/health")

    assert response.status_code == 503
    assert response.json()["database"] == {"readable": False, "chunks": None}


def test_the_schema_is_generated_from_the_models(app_factory):
    """The OpenAPI document describes the request and response shapes."""
    app, _ = app_factory()

    schema = request(app, "GET", "/openapi.json").json()

    components = schema["components"]["schemas"]
    assert set(components["SearchRequest"]["properties"]) == {"query", "limit"}
    assert set(components["SearchResponse"]["properties"]) == {
        "query",
        "results",
        "confidence",
    }
    assert set(components["ConfidenceModel"]["properties"]) == {
        "top_score",
        "margin",
        "lexical_dense_agree",
        "unmatched_terms",
    }


def test_startup_fails_loudly_when_the_store_is_missing(tmp_path):
    """Pointed at nothing, the service refuses to start."""
    app = create_app(
        resources=lambda: open_resources(
            tmp_path / "nowhere.db", tmp_path / "chroma", warm_models=False
        )
    )

    with pytest.raises(StartupError, match="no document store"):
        request(app, "GET", "/health")


def test_startup_fails_loudly_when_the_store_has_no_chunks(tmp_path):
    """An empty corpus fails at startup rather than answering with nothing."""
    database = tmp_path / "corpus.db"
    connect(database).close()

    with pytest.raises(StartupError, match="no chunks"):
        open_resources(database, tmp_path / "chroma", warm_models=False)


def test_startup_says_how_to_install_the_models(tmp_path, ingest, monkeypatch):
    """Without the models extra, startup names the command that fixes it."""
    database = tmp_path / "corpus.db"
    connection = connect(database)
    ingest(connection, "rev-b-schedule")
    connection.close()
    # A None entry in sys.modules is how the import system records "this
    # module is not importable", so this stands in for the extra being
    # absent whether or not it is installed here.
    monkeypatch.setitem(sys.modules, "corpus_query.models.embedder", None)

    with pytest.raises(StartupError, match="uv sync --extra models"):
        open_resources(database, tmp_path / "chroma")


def test_open_resources_opens_the_store_and_the_index(tmp_path, ingest):
    """A real store and a real index, opened once, with no model loaded."""
    database = tmp_path / "corpus.db"
    connection = connect(database)
    ingest(connection, "rev-b-schedule")
    connection.close()

    resources = open_resources(database, tmp_path / "chroma", warm_models=False)

    try:
        (chunks,) = resources.connection.execute(
            "SELECT count(*) FROM chunks"
        ).fetchone()
        assert chunks >= 1
        # Nothing is enriched, so no chunk has an embedding and the index
        # is correctly empty rather than missing.
        assert resources.collection.count() == 0
    finally:
        resources.close()
