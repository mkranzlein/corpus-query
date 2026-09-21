"""Tests for tracing the query path into the usage database.

The application, the graph, the retrieval tool, and the retrieval pipeline are
the real ones. Ranking runs for real too, over a three-chunk store with a
real vector index; only the embedder and the cross-encoder are stubbed, the
way the retrieval tests stub them, and the chat model is scripted. Spans land
in the temporary usage database the suite points every test at, and are read
back from it as rows — which is how anyone looking at a bad answer would read
them.

Nothing here loads a model, reaches Ollama, or calls anything hosted.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import Any

import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from test_agent_answer import ScriptedModel, answered, says, searches, verified
from test_answer_stream import HANG, STREAM, HangingModel, events, names, walk_away
from test_api import no_agent, request
from test_retrieval_search import (
    _fake_embed,
    _insert_chunk,
    _insert_document,
    _score_by_shared_words,
    _vector,
)

from corpus_query import tracing
from corpus_query.agent.graph import Agent, build_graph
from corpus_query.agent.retrieval import in_process_client, search_tool
from corpus_query.agent.runtime import correction_recorder, open_agent
from corpus_query.api.app import Resources, create_app
from corpus_query.retrieval import index as index_module
from corpus_query.retrieval.search import search
from corpus_query.store import capture, spans
from corpus_query.store.db import connect
from corpus_query.store.spans import SpanRow

#: The pipeline ``/search`` runs in these tests: the real one, with the
#: query embedded along the first axis and passages scored by the words they
#: share with the query.
RETRIEVE = partial(search, embed=_fake_embed(_vector(0)), rerank=_score_by_shared_words)

QUESTION = "Where are the rev B boards?"


@dataclass
class IdentifiedModel(ScriptedModel):
    """A scripted model that says what it is, the way a real backend does."""

    def _get_ls_params(self, **kwargs: Any) -> dict[str, Any]:
        """Report the provider and model, as LangChain's Ollama model does."""
        return {
            "ls_provider": "ollama",
            "ls_model_name": "granite4.1:8b",
            "ls_temperature": 0.0,
        }


def metered(message: AIMessage, used: int = 100, wrote: int = 20) -> AIMessage:
    """Give a scripted reply the metadata a real Ollama reply carries."""
    return message.model_copy(
        update={
            "usage_metadata": {
                "input_tokens": used,
                "output_tokens": wrote,
                "total_tokens": used + wrote,
            },
            "response_metadata": {"model_name": "granite4.1:8b", "done_reason": "stop"},
        }
    )


def a_corpus(tmp_path) -> tuple[sqlite3.Connection, Any]:
    """Build a three-chunk store and its vector index."""
    connection = connect(":memory:")
    document = _insert_document(
        connection, "rev-b-schedule", title="Rev B schedule", attendees=["Marcus"]
    )
    _insert_chunk(
        connection, document, 0, "The connector lead time slipped.", _vector(0)
    )
    _insert_chunk(
        connection, document, 1, "Marcus put the boards two weeks out.", _vector(1)
    )
    _insert_chunk(connection, document, 2, "Sofia owns the thermal review.", _vector(2))
    return connection, index_module.build_index(connection, tmp_path / "chroma")


def scripted(model: ScriptedModel):
    """Open the agent on a scripted model, the way the answering tests do."""

    @asynccontextmanager
    async def open_scripted(app):
        client = in_process_client(app)
        try:
            yield Agent(
                graph=build_graph(
                    model,
                    [search_tool(client)],
                    checkpointer=InMemorySaver(),
                    record_correction=correction_recorder(),
                )
            )
        finally:
            await client.aclose()

    return open_scripted


def traced_app(tmp_path, agent):
    """Build the application over a real store, index, and pipeline."""
    connection, collection = a_corpus(tmp_path)
    return create_app(
        resources=lambda: Resources(
            connection=connection, collection=collection, captured=capture.connect()
        ),
        search=RETRIEVE,
        agent=agent,
    )


def recorded_traces() -> list[list[SpanRow]]:
    """Read every trace back out of the usage database, oldest first."""
    connection = spans.connect()
    try:
        return [
            spans.trace(connection, trace_id)
            for trace_id in reversed(spans.traces(connection))
        ]
    finally:
        connection.close()


def one(rows: list[SpanRow], name: str) -> SpanRow:
    """Return the only span of a trace with that name."""
    [row] = [row for row in rows if row.name == name]
    return row


def children(rows: list[SpanRow], parent: SpanRow) -> list[SpanRow]:
    """Return the spans directly under one span, in the order they started."""
    return [row for row in rows if row.parent_span_id == parent.span_id]


def test_a_search_emits_a_span_per_stage_carrying_its_numbers(tmp_path) -> None:
    """Each stage of ranking is a span, and the whole says why each ranked."""
    body = request(
        traced_app(tmp_path, no_agent),
        "POST",
        "/search",
        json={"query": "connector lead time", "limit": 2},
    ).json()

    [rows] = recorded_traces()
    retrieval = one(rows, "retrieval corpus")
    assert retrieval.parent_span_id is None
    assert {row.name for row in children(rows, retrieval)} == {
        "lexical_search",
        "embeddings",
        "dense_search",
        "fuse",
        "rerank",
    }
    assert all(row.end_time_unix_nano >= row.start_time_unix_nano for row in rows)

    explained = retrieval.attributes
    assert explained["gen_ai.operation.name"] == "retrieval"
    assert explained["gen_ai.data_source.id"] == "corpus"
    assert explained["gen_ai.retrieval.top_k"] == 2
    assert explained["gen_ai.retrieval.query.text"] == "connector lead time"
    assert explained["corpus_query.retrieval.chunk_ids"] == [
        row["chunk_id"] for row in body["results"]
    ]
    assert explained["corpus_query.retrieval.rerank_scores"] == [
        row["rerank_score"] for row in body["results"]
    ]
    # Only the first chunk shares a word with the query, so lexical search
    # proposed it alone; the query vector points along its axis, so dense
    # search put it first too. The runner-up was proposed by dense only.
    assert explained["corpus_query.retrieval.lexical_ranks"] == [1, 0]
    assert explained["corpus_query.retrieval.dense_ranks"][0] == 1
    assert explained["corpus_query.retrieval.fused_ranks"][0] == 1
    # The confidence signals are the response's own, carried over.
    confidence = body["confidence"]
    assert explained["corpus_query.confidence.top_score"] == confidence["top_score"]
    assert explained["corpus_query.confidence.margin"] == confidence["margin"]
    assert (
        explained["corpus_query.confidence.lexical_dense_agree"]
        is confidence["lexical_dense_agree"]
        is True
    )
    assert explained["corpus_query.confidence.unmatched_terms"] == []

    stages = {row.name: row.attributes for row in children(rows, retrieval)}
    assert stages["lexical_search"]["corpus_query.retrieval.hit_count"] == 1
    assert stages["embeddings"]["gen_ai.operation.name"] == "embeddings"
    assert stages["embeddings"]["gen_ai.embeddings.dimension.count"] == 3
    assert stages["dense_search"]["corpus_query.retrieval.hit_count"] == 3
    assert stages["fuse"]["corpus_query.retrieval.hit_count"] == 3
    assert stages["rerank"]["corpus_query.rerank.candidate_count"] == 3
    assert stages["rerank"]["corpus_query.retrieval.hit_count"] == 2


def answering(model: ScriptedModel) -> list[AIMessage]:
    """Script a turn that searches once, drafts, verifies, and routes."""
    return [
        metered(searches("connector lead time")),
        metered(says("Marcus put the boards two weeks out."), used=300, wrote=12),
        verified(),
        answered(),
    ]


def test_an_answer_emits_a_span_for_each_model_and_tool_call(tmp_path) -> None:
    """The run, each model call, and the search it made form one tree."""
    model = IdentifiedModel([])
    model.replies = answering(model)
    body = request(
        traced_app(tmp_path, scripted(model)),
        "POST",
        "/answer",
        json={"question": QUESTION},
    ).json()

    [rows] = recorded_traces()
    run = one(rows, "invoke_agent corpus-query")
    assert run.parent_span_id is None
    assert run.status_code == "UNSET"
    assert run.attributes["gen_ai.operation.name"] == "invoke_agent"
    assert run.attributes["gen_ai.conversation.id"] == body["thread_id"]
    assert run.attributes["corpus_query.answer_id"] == body["answer_id"]
    assert run.attributes["corpus_query.answer.searches"] == 1

    under_run = children(rows, run)
    assert [row.name for row in under_run] == [
        "chat granite4.1:8b",
        "execute_tool search_corpus",
        "chat granite4.1:8b",
        "chat granite4.1:8b",
        "chat granite4.1:8b",
    ]
    chats = [row for row in under_run if row.name.startswith("chat")]
    assert [row.attributes["corpus_query.agent.step"] for row in chats] == [
        "think",
        "think",
        "verify",
        "route",
    ]
    for chat in chats:
        assert chat.kind == "CLIENT"
        assert chat.attributes["gen_ai.operation.name"] == "chat"
        assert chat.attributes["gen_ai.provider.name"] == "ollama"
        assert chat.attributes["gen_ai.request.model"] == "granite4.1:8b"
        assert chat.attributes["gen_ai.request.temperature"] == 0.0
        assert chat.attributes["gen_ai.conversation.id"] == body["thread_id"]
    drafted = chats[1].attributes
    assert drafted["gen_ai.response.model"] == "granite4.1:8b"
    assert drafted["gen_ai.response.finish_reasons"] == ["stop"]
    assert drafted["gen_ai.usage.input_tokens"] == 300
    assert drafted["gen_ai.usage.output_tokens"] == 12

    tool = one(rows, "execute_tool search_corpus")
    assert tool.attributes["gen_ai.operation.name"] == "execute_tool"
    assert tool.attributes["gen_ai.tool.name"] == "search_corpus"
    assert tool.attributes["gen_ai.tool.call.id"] == "call-1"
    assert tool.attributes["corpus_query.retrieval.result_count"] == 3
    assert "corpus_query.confidence.top_score" in tool.attributes
    # The search the tool made over HTTP is inside the tool's span, and
    # ranking inside that.
    [retrieval] = children(rows, tool)
    assert retrieval.name == "retrieval corpus"
    assert len(children(rows, retrieval)) == 5


def test_the_trace_id_is_on_the_answer_the_row_is_written_from(tmp_path) -> None:
    """Whoever records the answer has the trace it was produced under."""
    database = tmp_path / "usage.db"

    async def run():
        with tracing.open_tracing(database):
            async with open_agent(
                FastAPI(),
                model=ScriptedModel([says("Two weeks out.")]),
                checkpoint_database=database,
            ) as agent:
                return await agent.answer(QUESTION)

    answer = asyncio.run(run())

    assert len(answer.trace_id) == 32
    [rows] = recorded_traces()
    run_span = one(rows, "invoke_agent corpus-query")
    assert run_span.trace_id == answer.trace_id
    assert run_span.attributes["corpus_query.answer_id"] == answer.answer_id


def test_a_streamed_answer_is_traced_like_a_json_one(tmp_path) -> None:
    """Streaming is a way of delivering the answer, not a different run."""

    def traced(headers: dict[str, str]) -> list[str]:
        model = IdentifiedModel([])
        model.replies = answering(model)
        request(
            traced_app(tmp_path, scripted(model)),
            "POST",
            "/answer",
            json={"question": QUESTION},
            headers=headers,
        )
        return [row.name for row in recorded_traces()[-1]]

    assert traced(STREAM) == traced({})


@pytest.mark.parametrize(
    ("params", "backend", "model_name"),
    [
        (
            {"ls_provider": "ollama", "ls_model_name": "granite4.1:8b"},
            "ollama",
            "granite4.1:8b",
        ),
        (
            {
                "ls_provider": "amazon_bedrock",
                "ls_model_name": "us.anthropic.claude-sonnet-4-6",
            },
            "aws.bedrock",
            "us.anthropic.claude-sonnet-4-6",
        ),
    ],
)
@pytest.mark.parametrize("headers", [{}, STREAM], ids=["json", "stream"])
def test_the_answer_row_links_to_its_trace_and_names_what_answered(
    tmp_path, monkeypatch, params, backend, model_name, headers
) -> None:
    """The row's trace id finds the spans, and its numbers agree with them.

    Both ways of asking write the row the same way, and the backend on it is
    whichever model the graph actually ran on — here each of the project's
    two, as a scripted model reporting itself the way each one does.
    """
    model = IdentifiedModel([])
    model.replies = answering(model)
    monkeypatch.setattr(model, "_get_ls_params", lambda **kwargs: params)
    request(
        traced_app(tmp_path, scripted(model)),
        "POST",
        "/answer",
        json={"question": QUESTION},
        headers=headers,
    )

    connection = capture.connect()
    try:
        [row] = connection.execute("SELECT * FROM answers").fetchall()
        linked = [
            name
            for (name,) in connection.execute(
                "SELECT s.name FROM answers AS a "
                "JOIN spans AS s ON s.trace_id = a.trace_id "
                "ORDER BY s.start_time_unix_nano"
            )
        ]
    finally:
        connection.close()
    [rows] = recorded_traces()
    run = one(rows, "invoke_agent corpus-query")
    tool = one(rows, "execute_tool search_corpus")

    assert row["trace_id"] == run.trace_id
    assert linked == [span.name for span in rows]
    assert row["backend"] == backend
    assert row["model"] == model_name
    assert row["searches"] == 1
    assert row["top_score"] == tool.attributes["corpus_query.confidence.top_score"]
    assert row["margin"] == tool.attributes["corpus_query.confidence.margin"]
    # The answer is the second chunk of the three, word for word.
    assert row["citation_coverage"] == 1.0
    duration = (run.end_time_unix_nano - run.start_time_unix_nano) / 1e6
    assert 0 <= row["latency_ms"] <= duration + 1


def test_a_stream_the_client_walks_away_from_ends_its_spans(tmp_path) -> None:
    """The run and the model call it interrupted both end, as cancelled."""
    model = HangingModel([searches("connector lead time"), HANG])
    app = traced_app(tmp_path, scripted(model))

    async def run() -> bytes:
        async with app.router.lifespan_context(app):
            return (await walk_away(app, model))[1]

    streamed = asyncio.run(run())

    assert b"event: answer" not in streamed
    [rows] = recorded_traces()
    run_span = one(rows, "invoke_agent corpus-query")
    assert run_span.status_code == "ERROR"
    assert run_span.attributes["error.type"] == "cancelled"
    first, interrupted = [row for row in rows if row.name == "chat"]
    assert first.status_code == "UNSET"
    assert interrupted.status_code == "ERROR"
    assert interrupted.attributes["error.type"] == "cancelled"
    # The search that finished before the client left is there, whole.
    assert one(rows, "execute_tool search_corpus").status_code == "UNSET"


def test_a_failed_step_is_recorded_as_one(tmp_path) -> None:
    """A search that raises ends its spans as errors, with what went wrong."""

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("index is gone")

    model = ScriptedModel([searches("connector lead time")])
    connection, collection = a_corpus(tmp_path)
    app = create_app(
        resources=lambda: Resources(
            connection=connection, collection=collection, captured=capture.connect()
        ),
        search=broken,
        agent=scripted(model),
    )
    stream = events(
        request(app, "POST", "/answer", json={"question": QUESTION}, headers=STREAM)
    )

    assert names(stream)[-1] == "error"
    [rows] = recorded_traces()
    tool = one(rows, "execute_tool search_corpus")
    assert tool.status_code == "ERROR"
    assert tool.attributes["error.type"] == "RuntimeError"
    assert [event["name"] for event in tool.events] == ["exception"]
    assert one(rows, "invoke_agent corpus-query").status_code == "ERROR"


def test_a_retried_call_is_a_sibling_of_the_one_that_failed(tmp_path) -> None:
    """Each attempt is its own span, beside the others, under one parent."""

    @dataclass
    class Flaky:
        """A model that fails once and then answers."""

        calls: int = 0

        async def ainvoke(self, messages: Any, **kwargs: Any) -> AIMessage:
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("model server went away")
            return says("Two weeks out.")

    identity = tracing.ModelIdentity(provider="ollama", model="granite4.1:8b")

    async def run() -> None:
        flaky = Flaky()
        with tracing.span("parent"):
            for _ in range(2):
                try:
                    await tracing.call_model(flaky, [], identity, "think")
                    return
                except ConnectionError:
                    continue

    with tracing.open_tracing(tmp_path / "usage.db"):
        asyncio.run(run())

    [rows] = recorded_traces()
    parent = one(rows, "parent")
    failed, succeeded = children(rows, parent)
    assert failed.name == succeeded.name == "chat granite4.1:8b"
    assert failed.status_code == "ERROR"
    assert failed.attributes["error.type"] == "ConnectionError"
    assert succeeded.status_code == "UNSET"


def test_with_tracing_off_the_query_path_still_answers(monkeypatch) -> None:
    """Turned off, nothing is recorded and nothing else changes."""
    monkeypatch.setenv(tracing.DISABLED_VARIABLE, "true")
    model = ScriptedModel([says("That is outside what this corpus covers.")])

    @asynccontextmanager
    async def opened(app):
        async with scripted(model)(app) as agent:
            yield agent

    app = create_app(
        resources=lambda: Resources(
            connection=connect(":memory:"),
            collection=None,
            captured=capture.connect(),
        ),
        agent=opened,
    )
    answers: list[Any] = []

    async def run() -> None:
        async with app.router.lifespan_context(app):
            answers.append(await app.state.agent.answer("What is the capital?"))

    asyncio.run(run())

    assert answers[0].answer == "That is outside what this corpus covers."
    assert answers[0].trace_id == ""
    connection = sqlite3.connect(capture.usage_database())
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert "spans" not in tables


def test_the_console_is_one_variable_away(tmp_path, capsys) -> None:
    """Spans are printed as they end, as well as written to the database."""
    recording = tracing.open_tracing(
        tmp_path / "usage.db", env={tracing.CONSOLE_VARIABLE: "1"}
    )
    with recording:
        with tracing.span("printed"):
            pass

    assert [type(exporter).__name__ for exporter in recording.exporters] == [
        "UsageDatabaseExporter",
        "ConsoleSpanExporter",
    ]
    assert '"name": "printed"' in capsys.readouterr().out
    [rows] = recorded_traces()
    assert [row.name for row in rows] == ["printed"]


def test_an_otlp_endpoint_is_one_variable_away(tmp_path, monkeypatch) -> None:
    """Naming a collector adds an OTLP exporter pointed at it.

    Nothing is sent: the exporter connects when it has spans to send, and
    this opens and closes it without any.
    """
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    with tracing.open_tracing(tmp_path / "usage.db") as recording:
        pass

    assert [type(exporter).__name__ for exporter in recording.exporters] == [
        "UsageDatabaseExporter",
        "OTLPSpanExporter",
    ]


def test_spans_outside_an_open_tracing_are_not_recorded(tmp_path) -> None:
    """Closed, a span is a no-op with no trace id, wherever it is opened."""
    with tracing.open_tracing(tmp_path / "usage.db"):
        with tracing.span("kept") as kept:
            pass
    with tracing.span("dropped") as dropped:
        pass

    assert tracing.trace_id(kept)
    assert tracing.trace_id(dropped) == ""
    [rows] = recorded_traces()
    assert [row.name for row in rows] == ["kept"]


def test_spans_share_the_file_with_the_checkpointer_without_locking_it(
    tmp_path, monkeypatch, caplog
) -> None:
    """The real runtime, on one usage database, with spans written throughout.

    The checkpointer, the captured records, a correction written from inside
    the graph, and the span writer all use the same file here, through the
    same code the service runs. The batch delay is cut to a millisecond so
    the span writer is busy while the graph runs, rather than only once at
    shutdown, which is when writing from the event loop used to fail.
    """
    monkeypatch.setenv("OTEL_BSP_SCHEDULE_DELAY", "1")
    caplog.set_level(logging.ERROR)
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("The freeze is March 12th."),
            verified(),
            answered(),
            says("No, it moved to March 19th."),
            AIMessage(
                "",
                tool_calls=[
                    {
                        "name": "record_correction",
                        "args": {
                            "what_was_wrong": "It said March 12th.",
                            "what_is_right": "It moved to March 19th.",
                        },
                        "id": "fix",
                    }
                ],
            ),
        ]
    )
    app = traced_app(tmp_path, lambda application: open_agent(application, model))

    async def run() -> list[dict[str, Any]]:
        import httpx

        bodies = []
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://api.test"
            ) as client:
                first = await client.post(
                    "/answer", json={"question": "When is the firmware freeze?"}
                )
                bodies.append(first.json())
                second = await client.post(
                    "/answer",
                    json={
                        "question": "No, it moved to March 19th.",
                        "thread_id": bodies[0]["thread_id"],
                    },
                )
                bodies.append(second.json())
        return bodies

    first, second = asyncio.run(run())

    assert second["correction"]["answer_id"] == first["answer_id"]
    assert "could not write spans" not in caplog.text
    first_trace, second_trace = recorded_traces()
    assert (
        one(first_trace, "invoke_agent corpus-query").attributes[
            "corpus_query.answer_id"
        ]
        == (first["answer_id"])
    )
    assert one(second_trace, "execute_tool record_correction").attributes[
        "corpus_query.correction.recorded"
    ]


@pytest.mark.parametrize(
    ("params", "provider", "name"),
    [
        (
            {"ls_provider": "ollama", "ls_model_name": "granite4.1:8b"},
            "ollama",
            "chat granite4.1:8b",
        ),
        (
            {
                "ls_provider": "amazon_bedrock",
                "ls_model_name": "us.anthropic.claude-sonnet-4-6",
            },
            "aws.bedrock",
            "chat us.anthropic.claude-sonnet-4-6",
        ),
        ({}, "unknown", "chat"),
    ],
)
def test_a_model_is_named_as_the_conventions_name_it(params, provider, name) -> None:
    """LangChain's provider names become the conventions' ones."""

    class Reporting:
        def _get_ls_params(self) -> dict[str, Any]:
            return params

    identity = tracing.identify(Reporting())

    assert identity.provider == provider
    assert identity.span_name == name


def test_the_projects_backends_identify_themselves() -> None:
    """The real model classes report what the spans need, without a call."""
    from corpus_query.agent.model import load_chat_model

    identity = tracing.identify(load_chat_model("ollama", env={}))

    assert identity.provider == "ollama"
    assert identity.model == "granite4.1:8b"
    assert identity.temperature == 0.0
