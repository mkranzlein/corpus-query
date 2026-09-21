"""Tests for the query API.

These drive the real application in process, over ASGI, with no socket and no
server: httpx speaks to it through :class:`~httpx.ASGITransport`, so status
codes, validation errors, and JSON bodies are the genuine article rather than
a function's return value inspected directly.

Retrieval is stubbed throughout. What ranks above what is settled in the
retrieval tests; what is under test here is the HTTP layer — shapes, status
codes, and what happens when the input or the corpus is not what was hoped
for. The agent is stubbed out entirely, for the same reason and because
opening the real one would load a chat model and a thread store neither
``/search`` nor ``/health`` touches; it has tests of its own. Nothing here
loads a model, so none of it needs the models extra.

The capture endpoints are not stubbed either: they write to a real SQLite
file under ``tmp_path`` and read back out of it, because what is worth
asserting about them is mostly what the file does — that an orphan is refused
and that a row comes back readable without a second call.

The browser application is not stubbed. It is committed, so the tests serve
the same bytes a clone does, which is what makes "the page is served" worth
asserting at all. Nothing here runs Node.
"""

from __future__ import annotations

import asyncio
import re
import sys
from contextlib import asynccontextmanager
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
from corpus_query.store import capture
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


def session_requests(app, calls: list[tuple[str, str]]) -> list[httpx.Response]:
    """Make several requests against one application, within one lifespan.

    :func:`request` opens and closes the application per call, which closes
    the store connection with it, so a test that wants to see two endpoints
    answer the same running service asks here instead.

    Args:
        app: The application to drive.
        calls: The method and path of each request, in order.

    Returns:
        One response per call, in the same order.
    """

    async def run() -> list[httpx.Response]:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://api.test"
            ) as client:
                return [await client.request(method, url) for method, url in calls]

    return asyncio.run(run())


def captured_records():
    """Open the capture store the application records into.

    The default usage database is redirected to ``tmp_path`` for every test,
    so this opens a throwaway file rather than the project's own. The
    application closes it when its lifespan ends.

    Returns:
        An open connection to the captured records.
    """
    return capture.connect()


@asynccontextmanager
async def no_agent(app):
    """Stand in for the agent, opening nothing.

    Args:
        app: The application, ignored.

    Yields:
        None. Nothing here asks ``/answer`` anything.
    """
    yield None


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


def a_result(
    rank: int = 1,
    chunk_id: int = 7,
    score: float = 4.5,
    document_slug: str = "rev-b-schedule",
    title: str = "Rev B schedule",
    source_kind: str = TRANSCRIPT,
    author: str | None = None,
    attendees: list[str] | None = None,
    location: str = "turns 0-1",
) -> Result:
    """Build one ranked result with every field populated.

    The defaults are a transcript, which is the corpus's commonest source
    and the one that carries attendees rather than an author. The people
    fields are parameters because what a passage names is what decides who
    a question routes to.
    """
    return Result(
        chunk_id=chunk_id,
        text="Marcus: Two weeks out, assuming the connectors land.",
        document_slug=document_slug,
        source_kind=source_kind,
        title=title,
        document_date="2026-03-04",
        author=author,
        attendees=(
            ["Priya", "Marcus", "Sofia"]
            if attendees is None and author is None
            else list(attendees or [])
        ),
        location=location,
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
            connection=store,
            collection=collection or FakeCollection(),
            captured=captured_records(),
        )
        app = create_app(resources=lambda: resources, search=stub, agent=no_agent)
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
    assert result["attendees"] == ["Priya", "Marcus", "Sofia"]
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
        ),
        agent=no_agent,
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


def test_the_frontend_is_served_at_the_root(app_factory):
    """A browser asking for the site gets the built application."""
    app, _ = app_factory()

    response = request(app, "GET", "/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="root"' in response.text


def test_the_bundled_assets_are_served(app_factory):
    """The script the page asks for is there, at the path the page names."""
    app, _ = app_factory()
    [script] = re.findall(r'src="\./(assets/[^"]+\.js)"', request(app, "GET", "/").text)

    response = request(app, "GET", f"/{script}")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_serving_the_page_does_not_shadow_the_endpoints(app_factory):
    """The mount is at ``/`` and still comes second to everything above it."""
    app, _ = app_factory()

    health, schema, page = session_requests(
        app, [("GET", "/health"), ("GET", "/openapi.json"), ("GET", "/")]
    )

    assert (health.status_code, schema.status_code) == (200, 200)
    assert health.json()["status"] == "ok"
    assert "/search" in schema.json()["paths"]
    assert page.headers["content-type"].startswith("text/html")


def test_an_unknown_path_is_still_a_404(app_factory):
    """Serving a page at the root does not turn every path into that page."""
    app, _ = app_factory()

    assert request(app, "GET", "/nowhere").status_code == 404


def test_a_missing_bundle_does_not_stop_the_api(tmp_path, store):
    """Without a built page the endpoints work and the root says why."""
    resources = Resources(
        connection=store, collection=FakeCollection(), captured=captured_records()
    )
    app = create_app(
        resources=lambda: resources,
        search=StubSearch(SearchResult(results=[], confidence=a_confidence())),
        agent=no_agent,
        static_dir=tmp_path / "never-built",
    )

    root, health = session_requests(app, [("GET", "/"), ("GET", "/health")])

    assert root.status_code == 503
    assert "npm --prefix frontend run build" in root.text
    assert health.status_code == 200


@pytest.fixture
def records_app(tmp_path):
    """Return an app recording into a usage database, and where that is.

    The application is given a fresh document store per startup, because
    :func:`request` runs one request inside its own lifespan and closes
    everything after. The captured records are a file rather than memory,
    so a write made by one request is there for the next one to read — and
    for the test to read directly.

    Returns:
        The application, and the path its records go to.
    """
    path = tmp_path / "records.db"

    def open_them() -> Resources:
        return Resources(
            connection=connect(":memory:"),
            collection=FakeCollection(),
            captured=capture.connect(path),
        )

    app = create_app(
        resources=open_them,
        search=StubSearch(SearchResult(results=[], confidence=a_confidence())),
        agent=no_agent,
    )
    return app, path


def an_answer(path, **overrides: Any) -> str:
    """Record one answer in the file the application writes to.

    Args:
        path: The usage database the application was pointed at.
        **overrides: Fields of the answer row to set.

    Returns:
        The new answer's id.
    """
    connection = capture.connect(path)
    try:
        return capture.record_answer(
            connection,
            **{
                "query": "Where are the rev B boards?",
                "answer": "Marcus put them two weeks out.",
                "citations": [],
                "thread_id": "thread-1",
                "abstained": False,
            }
            | overrides,
        )
    finally:
        connection.close()


def test_a_correction_is_recorded_against_an_answer(records_app):
    """Both halves come back on the created record, with what they are about."""
    app, path = records_app
    answer_id = an_answer(path)

    response = request(
        app,
        "POST",
        "/corrections",
        json={
            "answer_id": answer_id,
            "what_was_wrong": "It said the freeze is March 12th.",
            "what_is_right": "The freeze moved to March 19th.",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["answer_id"] == answer_id
    assert body["what_was_wrong"] == "It said the freeze is March 12th."
    assert body["what_is_right"] == "The freeze moved to March 19th."
    assert body["question"] == "Where are the rev B boards?"
    assert body["answer"] == "Marcus put them two weeks out."
    assert body["created_at"]


@pytest.mark.parametrize("verdict", ["up", "down"])
def test_feedback_records_a_verdict(records_app, verdict):
    """A thumbs up or down is recorded, with the note when there is one."""
    app, path = records_app
    answer_id = an_answer(path)

    response = request(
        app,
        "POST",
        "/feedback",
        json={
            "answer_id": answer_id,
            "verdict": verdict,
            "note": "cited the wrong meeting",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["verdict"] == verdict
    assert body["note"] == "cited the wrong meeting"


def test_feedback_does_not_need_a_note(records_app):
    """A bare verdict is a complete record, and it is not a correction."""
    app, path = records_app
    answer_id = an_answer(path)

    body = request(
        app, "POST", "/feedback", json={"answer_id": answer_id, "verdict": "down"}
    ).json()

    assert body["note"] is None


@pytest.mark.parametrize(
    "url_and_payload",
    [
        pytest.param(
            ("/corrections", {"what_was_wrong": "the date", "what_is_right": "March"}),
            id="correction",
        ),
        pytest.param(("/feedback", {"verdict": "up"}), id="feedback"),
    ],
)
def test_a_write_against_an_unknown_answer_is_a_404(records_app, url_and_payload):
    """An orphan is refused, and the refusal says what the id should be."""
    app, _ = records_app
    url, payload = url_and_payload

    response = request(app, "POST", url, json={"answer_id": "nope"} | payload)

    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_a_verdict_that_is_neither_up_nor_down_is_a_422(records_app):
    """The two verdicts are the contract, and the schema says so."""
    app, path = records_app
    answer_id = an_answer(path)

    response = request(
        app, "POST", "/feedback", json={"answer_id": answer_id, "verdict": "sideways"}
    )

    assert response.status_code == 422
    assert "verdict" in str(response.json()["detail"])


@pytest.mark.parametrize("field", ["what_was_wrong", "what_is_right"])
def test_a_correction_needs_both_halves(records_app, field):
    """Half a correction carries nothing to act on, so it is refused."""
    app, path = records_app
    answer_id = an_answer(path)
    payload = {
        "answer_id": answer_id,
        "what_was_wrong": "the date",
        "what_is_right": "March 19th",
    } | {field: "   "}

    response = request(app, "POST", "/corrections", json=payload)

    assert response.status_code == 422
    assert field in str(response.json()["detail"])


def test_the_reads_come_back_most_recent_first(records_app):
    """A reader catching up gets the newest first, not the oldest."""
    app, path = records_app
    answer_id = an_answer(path)
    for note in ("first", "second"):
        request(
            app,
            "POST",
            "/feedback",
            json={"answer_id": answer_id, "verdict": "down", "note": note},
        )

    body = request(app, "GET", "/feedback").json()

    assert [row["note"] for row in body["feedback"]] == ["second", "first"]


def test_a_read_carries_enough_to_be_read_without_a_second_call(records_app):
    """Each row names the question and the answer it was recorded against."""
    app, path = records_app
    answer_id = an_answer(path, query="What is the tolerance?", abstained=True)
    connection = capture.connect(path)
    try:
        capture.record_gap(connection, answer_id)
    finally:
        connection.close()
    request(
        app,
        "POST",
        "/corrections",
        json={
            "answer_id": answer_id,
            "what_was_wrong": "the tolerance",
            "what_is_right": "it is 0.2mm",
        },
    )

    gaps = request(app, "GET", "/gaps").json()["gaps"]
    corrections = request(app, "GET", "/corrections").json()["corrections"]

    for [row] in (gaps, corrections):
        assert row["question"] == "What is the tolerance?"
        assert row["answer"] == "Marcus put them two weeks out."
        assert row["thread_id"] == "thread-1"
        assert row["abstained"] is True


def test_reading_before_anything_was_recorded_is_an_empty_list(records_app):
    """Nothing recorded is an answer, not a missing resource."""
    app, _ = records_app

    for url, key in (
        ("/gaps", "gaps"),
        ("/corrections", "corrections"),
        ("/feedback", "feedback"),
    ):
        response = request(app, "GET", url)
        assert response.status_code == 200
        assert response.json()[key] == []


def test_a_read_stops_at_the_limit_it_was_given(records_app):
    """These reads are for catching up, not for exporting the table."""
    app, path = records_app
    answer_id = an_answer(path)
    for note in ("first", "second", "third"):
        request(
            app,
            "POST",
            "/feedback",
            json={"answer_id": answer_id, "verdict": "up", "note": note},
        )

    body = request(app, "GET", "/feedback?limit=2").json()

    assert [row["note"] for row in body["feedback"]] == ["third", "second"]


def test_an_unbounded_read_is_refused(records_app):
    """An unbounded limit is a table export behind a page of prose."""
    app, _ = records_app

    assert request(app, "GET", "/gaps?limit=100000").status_code == 422


def test_what_is_recorded_goes_nowhere_near_the_corpus(records_app):
    """The records live in their own file, which holds no corpus tables."""
    app, path = records_app
    answer_id = an_answer(path)

    request(app, "POST", "/feedback", json={"answer_id": answer_id, "verdict": "up"})

    connection = capture.connect(path)
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert {"answers", "gaps", "corrections", "feedback"} <= tables
    assert "chunks" not in tables
