"""Tests for ``/answer`` as a stream of server-sent events.

The application, the graph, and the retrieval tool are the real ones, driven
the way the answering tests drive them: a scripted model stands in for the
chat model, and ranking is stubbed. What is under test is what the graph's
progress looks like on the wire — which events arrive, in what order, what
they carry — and what happens to a stream that does not finish: one the run
failed partway through, and one the client walked away from.

The client walking away is driven over raw ASGI rather than through httpx,
because what matters is the disconnect message the server sees, and that is
something only a hand-written ``receive`` can send at a chosen moment.

Nothing here loads a model, reaches Ollama, or calls anything hosted.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from corpus_query.agent.graph import Agent, build_graph
from corpus_query.api.models import AnswerResponse
from test_agent_answer import (
    ScriptedModel,
    answered,
    answering_app,
    found,
    recorded,
    rejects,
    says,
    searches,
    verified,
)
from test_api import StubSearch, request

STREAM = {"accept": "text/event-stream"}


def events(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    """Read a server-sent event stream back into events.

    Args:
        response: A response whose body is ``text/event-stream``.

    Returns:
        Each event's type and its decoded data, in the order sent.
    """
    parsed = []
    for block in response.text.split("\n\n"):
        if not block.strip():
            continue
        fields: dict[str, list[str]] = {}
        for line in block.splitlines():
            name, _, value = line.partition(": ")
            fields.setdefault(name, []).append(value)
        parsed.append((fields["event"][0], json.loads("\n".join(fields["data"]))))
    return parsed


def names(stream: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Return just the event types of a stream, in order."""
    return [name for name, _ in stream]


def test_a_streamed_answer_reports_each_step_then_the_answer() -> None:
    """Retrieval, drafting, and verification each arrive as they happen."""
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("Marcus put the rev B boards two weeks out."),
            verified(),
            answered(),
        ]
    )
    response = request(
        answering_app(model, StubSearch(result=found())),
        "POST",
        "/answer",
        json={"question": "Where are the rev B boards?"},
        headers=STREAM,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    stream = events(response)
    assert names(stream) == [
        "started",
        "drafting",
        "searching",
        "searched",
        "drafting",
        "verifying",
        "verified",
        "routing",
        "answer",
    ]
    data = dict(stream)
    assert data["searching"] == {"query": "connector lead time"}
    assert data["searched"]["query"] == "connector lead time"
    assert [row["document_slug"] for row in data["searched"]["citations"]] == [
        "rev-b-schedule"
    ]
    assert data["verified"] == {"verification": None, "redraft": False}
    # The thread is known before anything has run, and the answer that
    # arrives last belongs to it.
    answer = AnswerResponse.model_validate(data["answer"])
    assert answer.thread_id == data["started"]["thread_id"]
    assert answer.answer == "Marcus put the rev B boards two weeks out."
    assert answer.searches == 1
    assert answer.abstained is False
    # Streaming is a way of delivering the answer, not a different kind of
    # answer: it is recorded like any other.
    [row] = recorded()["answers"]
    assert row["id"] == answer.answer_id


def test_a_rejected_draft_is_reported_before_the_redraft() -> None:
    """A redraft shows as a second round of drafting, with the reason first."""
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("Marcus put the rev B boards two weeks out, and they are blue."),
            rejects("they are blue"),
            says("Marcus put the rev B boards two weeks out."),
            verified(),
            answered(),
        ]
    )
    stream = events(
        request(
            answering_app(model, StubSearch(result=found())),
            "POST",
            "/answer",
            json={"question": "Where are the rev B boards?"},
            headers=STREAM,
        )
    )

    assert names(stream)[4:] == [
        "drafting",
        "verifying",
        "verified",
        "drafting",
        "verifying",
        "verified",
        "routing",
        "answer",
    ]
    first, second = [data for name, data in stream if name == "verified"]
    assert first == {
        "verification": {"rejected": ["they are blue"], "exhausted": False},
        "redraft": True,
    }
    assert second == {"verification": None, "redraft": False}


def test_a_question_answered_without_searching_skips_the_checks() -> None:
    """No search, no passages: nothing to verify and nobody to route to."""
    model = ScriptedModel([says("That is outside what this corpus covers.")])
    stream = events(
        request(
            answering_app(model, StubSearch(result=found())),
            "POST",
            "/answer",
            json={"question": "What is the capital of France?"},
            headers=STREAM,
        )
    )

    assert names(stream) == ["started", "drafting", "answer"]


def test_without_asking_for_a_stream_the_answer_is_one_json_body() -> None:
    """The same question, without the header, is the response it always was."""

    def asked_with(headers: dict[str, str]) -> httpx.Response:
        model = ScriptedModel(
            [
                searches("connector lead time"),
                says("Marcus put the rev B boards two weeks out."),
                verified(),
                answered(),
            ]
        )
        return request(
            answering_app(model, StubSearch(result=found())),
            "POST",
            "/answer",
            json={"question": "Where are the rev B boards?"},
            headers=headers,
        )

    plain = asked_with({})
    wildcard = asked_with({"accept": "*/*"})
    streamed = dict(events(asked_with(STREAM)))["answer"]

    for response in (plain, wildcard):
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
    # Identical apart from the ids, which are minted per request.
    ids = {"thread_id", "answer_id"}
    for body in (plain.json(), wildcard.json()):
        assert body.keys() == streamed.keys()
        assert {k: v for k, v in body.items() if k not in ids} == {
            k: v for k, v in streamed.items() if k not in ids
        }


def test_an_invalid_question_is_refused_before_any_stream_starts() -> None:
    """Validation still answers with a status code, not an event."""
    response = request(
        answering_app(ScriptedModel([]), StubSearch(result=found())),
        "POST",
        "/answer",
        json={"question": "   "},
        headers=STREAM,
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json"


@dataclass
class FailingSearch:
    """A retrieval pipeline that has stopped working."""

    calls: list[str] = field(default_factory=list)

    def __call__(self, connection, collection, query, **kwargs) -> Any:
        """Record the call and fail it."""
        self.calls.append(query)
        raise RuntimeError("index is gone")


def test_a_failure_partway_arrives_as_an_error_event() -> None:
    """A run that fails mid-stream says so, rather than just stopping."""
    model = ScriptedModel([searches("connector lead time")])
    response = request(
        answering_app(model, FailingSearch()),
        "POST",
        "/answer",
        json={"question": "Where are the rev B boards?"},
        headers=STREAM,
    )

    assert response.status_code == 200
    stream = events(response)
    assert names(stream) == ["started", "drafting", "searching", "error"]
    assert "index is gone" in stream[-1][1]["detail"]
    # Nothing was answered, so nothing was recorded.
    assert recorded()["answers"] == []


def conversation_over_asgi(app, steps) -> list[Any]:
    """Run several steps against one application, in one startup.

    Args:
        app: The application to drive.
        steps: Coroutine functions, each taking the application, run in
            order.

    Returns:
        What each step returned.
    """

    async def run() -> list[Any]:
        async with app.router.lifespan_context(app):
            return [await step(app) for step in steps]

    return asyncio.run(run())


async def ask(app, payload: dict[str, Any]) -> dict[str, Any]:
    """Ask for one answer as a plain JSON request.

    Args:
        app: The application, already started.
        payload: The request body.

    Returns:
        The response body.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api.test"
    ) as client:
        response = await client.post("/answer", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_follow_up_after_a_failure_is_answered_cleanly() -> None:
    """The half-finished turn a failure leaves does not reach the next one."""
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("I can answer that one."),
        ]
    )
    app = answering_app(model, FailingSearch())
    thread: list[str] = []

    async def first(app) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.test"
        ) as client:
            response = await client.post(
                "/answer",
                json={"question": "Where are the rev B boards?"},
                headers=STREAM,
            )
        stream = events(response)
        assert names(stream)[-1] == "error"
        thread.append(stream[0][1]["thread_id"])

    async def second(app) -> dict[str, Any]:
        return await ask(app, {"question": "Who is Marcus?", "thread_id": thread[0]})

    _, body = conversation_over_asgi(app, [first, second])

    assert body["answer"] == "I can answer that one."
    assert body["thread_id"] == thread[0]
    # The failed turn left a search asked for and never answered. The
    # follow-up's prompt holds none of it: no rewrite was needed, because
    # there was no finished conversation to resolve against, and the model
    # was shown only the new question.
    prompt = model.prompts[-1]
    assert [type(message) for message in prompt[1:]] == [HumanMessage]
    assert prompt[-1].content == "Who is Marcus?"
    assert not any(isinstance(message, (AIMessage, ToolMessage)) for message in prompt)


class Hang:
    """A model reply that never comes, until the call is cancelled.

    Stands in for a local model partway through a slow draft. The moment
    the call starts is signalled, so a test can walk away at exactly that
    point, and whether the call was cancelled is recorded, so it can see
    that walking away actually stopped the work.
    """

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def wait(self) -> AIMessage:
        """Block until cancelled."""
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")  # pragma: no cover


@dataclass
class HangingModel(ScriptedModel):
    """A scripted model whose script can include a reply that never comes."""

    hang: Hang = field(default_factory=Hang)

    def bind_tools(self, tools: list[Any]) -> HangingBound:
        """Attach the tools, keeping the ability to hang."""
        bound = super().bind_tools(tools)
        return HangingBound(self, bound.tools)

    async def ainvoke(self, messages: list[Any], **kwargs: Any) -> AIMessage:
        """Return the next reply, or hang if that is what is next."""
        return await self.reply(messages, tools=[])

    async def reply(self, messages: list[Any], tools: list[str]) -> AIMessage:
        """Pop the next reply, hanging on :data:`HANG`."""
        message = self.next_reply(messages, tools=tools)
        if message is HANG:
            return await self.hang.wait()
        return message


@dataclass
class HangingBound:
    """The hanging model with its tools attached."""

    model: HangingModel
    tools: list[str]

    async def ainvoke(self, messages: list[Any], **kwargs: Any) -> AIMessage:
        """Return the next reply, or hang, for a call made with tools."""
        return await self.model.reply(messages, tools=self.tools)


#: Put in a script where the model should never reply.
HANG = AIMessage("never sent")


async def walk_away(app, model: HangingModel) -> tuple[str, bytes]:
    """Ask for a stream, and disconnect once the model is mid-draft.

    Driven over raw ASGI, as a server would call the application, so the
    disconnect is the message a real server sends when the socket closes.

    Args:
        app: The application, already started.
        model: The model, whose hang says when to disconnect.

    Returns:
        The thread the stream announced, and everything that was sent
        before the client left.
    """
    body = json.dumps({"question": "Where are the rev B boards?"}).encode()
    delivered = False
    sent: list[bytes] = []

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await model.hang.started.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.body":
            sent.append(message.get("body", b""))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/answer",
        "raw_path": b"/answer",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"api.test"),
            (b"content-type", b"application/json"),
            (b"accept", b"text/event-stream"),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("api.test", 80),
    }
    # A wedged run never returns. Bounding the wait turns that into a
    # failure rather than a suite that hangs.
    await asyncio.wait_for(app(scope, receive, send), timeout=10)
    streamed = b"".join(sent)
    started = streamed.split(b"\n\n", 1)[0]
    thread = json.loads(started.split(b"data: ", 1)[1])["thread_id"]
    return thread, streamed


def test_a_client_that_walks_away_stops_the_run() -> None:
    """Disconnecting mid-draft cancels the model call and records nothing."""
    model = HangingModel([searches("connector lead time"), HANG])
    app = answering_app(model, StubSearch(result=found()))

    async def step(app) -> tuple[str, bytes]:
        return await walk_away(app, model)

    [(_, streamed)] = conversation_over_asgi(app, [step])

    assert b"event: searched" in streamed
    assert b"event: answer" not in streamed
    assert model.hang.cancelled
    assert recorded()["answers"] == []


def test_the_thread_walked_away_from_still_answers() -> None:
    """The next question on an abandoned thread runs to completion."""
    model = HangingModel(
        [
            searches("connector lead time"),
            HANG,
            says("Marcus is the hardware lead."),
        ]
    )
    app = answering_app(model, StubSearch(result=found()))
    thread: list[str] = []

    async def first(app) -> None:
        thread.append((await walk_away(app, model))[0])

    async def second(app) -> dict[str, Any]:
        return await ask(app, {"question": "Who is Marcus?", "thread_id": thread[0]})

    _, body = conversation_over_asgi(app, [first, second])

    assert body["answer"] == "Marcus is the hardware lead."
    assert body["thread_id"] == thread[0]
    assert body["searches"] == 0
    # Only the question that finished was recorded.
    [row] = recorded()["answers"]
    assert row["query"] == "Who is Marcus?"
    # The abandoned turn's search and its passages are gone from the
    # conversation the model is shown.
    prompt = model.prompts[-1]
    assert [type(message) for message in prompt[1:]] == [HumanMessage]


def test_the_stream_is_described_in_the_schema() -> None:
    """The generated documentation says ``/answer`` can stream, and what."""
    schema = request(
        answering_app(ScriptedModel([]), StubSearch(result=found())),
        "GET",
        "/openapi.json",
    ).json()

    ok = schema["paths"]["/answer"]["post"]["responses"]["200"]
    assert set(ok["content"]) == {"application/json", "text/event-stream"}
    for name in ("searching", "searched", "drafting", "verifying", "answer", "error"):
        assert f"``{name}``" in ok["description"]


def test_an_unpersisted_graph_still_takes_a_thread_id() -> None:
    """With no checkpointer there is no earlier run to clear, and no error."""
    agent = Agent(graph=build_graph(ScriptedModel([says("Hello.")]), []))
    result = asyncio.run(agent.answer("Hi?", thread_id="thread-1"))

    assert result.answer == "Hello."
    assert result.thread_id == "thread-1"
