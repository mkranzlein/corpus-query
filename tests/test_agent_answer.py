"""Tests for the agent and the ``/answer`` endpoint.

These drive the real application, the real graph, and the real retrieval
tool. The only thing standing in is the model: a scripted fake that hands
back the messages a run would have produced. That is deliberate, and it is
where the line sits — what a model decides is not a thing a test can assert
on, but what the graph does with each decision is, and so is whether the tool
actually reached ``/search`` over HTTP.

It really is over HTTP. The tool posts through :class:`httpx.ASGITransport`
into the same application that is serving ``/answer``, so the search the agent
runs goes through routing, validation, and JSON serialization exactly as a
``curl`` would. Ranking itself is stubbed, for the same reason the API tests
stub it: what ranks above what is settled in the retrieval tests.

Nothing here loads a model, reaches Ollama, or calls anything hosted.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from corpus_query.agent.graph import Agent, build_graph
from corpus_query.agent.retrieval import (
    TOOL_NAME,
    citation,
    in_process_client,
    render_passages,
    search_tool,
)
from corpus_query.api.app import Resources, create_app
from corpus_query.retrieval.search import Confidence, SearchResult
from corpus_query.store.db import connect
from test_api import FakeCollection, StubSearch, a_confidence, a_result, request


@dataclass
class ScriptedModel:
    """A chat model that says what it was told to, in order.

    It implements the two things the graph asks of a chat model —
    ``bind_tools`` and ``ainvoke`` — and records what it was given: every
    prompt, the tools that were attached, and whether each call was made
    through the bound model or the bare one. A test can then assert on what
    the model was shown as well as on what the graph did with the reply.
    """

    replies: list[AIMessage]
    prompts: list[list[Any]] = field(default_factory=list)
    bound: list[Any] = field(default_factory=list)
    with_tools: list[bool] = field(default_factory=list)
    """One entry per call: whether the tools were attached for it."""

    def bind_tools(self, tools: list[Any]) -> BoundModel:
        """Record the tools and hand back the model they are attached to.

        Args:
            tools: What the graph attached.

        Returns:
            The same script, reached through a distinct object, so a test
            can tell a call made with tools from one made without.
        """
        self.bound = list(tools)
        return BoundModel(self)

    async def ainvoke(self, messages: list[Any], **kwargs: Any) -> AIMessage:
        """Return the next scripted reply, for a call made without tools."""
        return self.next_reply(messages, with_tools=False)

    def next_reply(self, messages: list[Any], with_tools: bool) -> AIMessage:
        """Record one call and pop the reply that answers it.

        Args:
            messages: The conversation so far, system prompt included.
            with_tools: Whether the caller had tools attached.

        Returns:
            The next message in the script.

        Raises:
            AssertionError: If the graph called the model more times than
                the script accounts for, which is a loop rather than a run.
        """
        self.prompts.append(list(messages))
        self.with_tools.append(with_tools)
        if not self.replies:
            raise AssertionError("the graph called the model past its script")
        return self.replies.pop(0)


@dataclass
class BoundModel:
    """The scripted model with its tools attached."""

    model: ScriptedModel

    async def ainvoke(self, messages: list[Any], **kwargs: Any) -> AIMessage:
        """Return the next scripted reply, for a call made with tools."""
        return self.model.next_reply(messages, with_tools=True)


def says(text: str) -> AIMessage:
    """Build a model reply that answers and calls nothing."""
    return AIMessage(text)


def answered() -> AIMessage:
    """Build the routing model's reply for an answer that settled it."""
    return AIMessage("ANSWERED")


def searches(query: str, call_id: str = "call-1") -> AIMessage:
    """Build a model reply that asks for one search.

    Args:
        query: What the model asks to search for.
        call_id: The tool call's id, which the tool message answers to.

    Returns:
        The reply, with one tool call on it.
    """
    return AIMessage(
        "",
        tool_calls=[{"name": TOOL_NAME, "args": {"query": query}, "id": call_id}],
    )


def answering_app(model: ScriptedModel, search: StubSearch):
    """Build the application, with the agent running on a scripted model.

    Args:
        model: What to answer with.
        search: What ``/search`` ranks with.

    Returns:
        The application, ready to be driven.
    """

    @asynccontextmanager
    async def open_scripted(app):
        """Open the agent against the scripted model and an in-memory thread store."""
        client = in_process_client(app)
        try:
            yield Agent(
                graph=build_graph(
                    model, [search_tool(client)], checkpointer=InMemorySaver()
                )
            )
        finally:
            await client.aclose()

    return create_app(
        resources=lambda: Resources(
            connection=connect(":memory:"), collection=FakeCollection()
        ),
        search=search,
        agent=open_scripted,
    )


def conversation(app, *payloads: dict[str, Any]) -> list[dict[str, Any]]:
    """Ask several questions of one application, in one startup.

    The helper in the API tests starts and stops the application around
    every request, which is right for a test of one endpoint and wrong here:
    the agent and its thread store are opened at startup, so a follow-up
    made that way would be asked of a fresh agent with no memory of the
    first question. A served process starts once and answers many.

    Args:
        app: The application to drive.
        *payloads: One request body per question, asked in order. Each may
            name the thread the one before it came back with.

    Returns:
        The response bodies, in the same order.
    """

    async def run() -> list[dict[str, Any]]:
        bodies = []
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://api.test"
            ) as client:
                for payload in payloads:
                    thread = payload.pop("_thread_from", None)
                    if thread is not None:
                        payload["thread_id"] = bodies[thread]["thread_id"]
                    response = await client.post("/answer", json=payload)
                    bodies.append(response.json())
        return bodies

    return asyncio.run(run())


def found(**overrides: Any) -> SearchResult:
    """Build a search result holding one ranked passage."""
    return SearchResult(results=[a_result(**overrides)], confidence=a_confidence())


def all_of(*results: Any) -> SearchResult:
    """Build a search result holding several ranked passages, best first."""
    return SearchResult(results=list(results), confidence=a_confidence())


def nothing() -> SearchResult:
    """Build a search result holding no passages at all."""
    return SearchResult(
        results=[],
        confidence=Confidence(
            top_score=None,
            margin=None,
            lexical_dense_agree=False,
            unmatched_terms=["kalamazoo"],
        ),
    )


def test_answers_a_question_the_corpus_covers() -> None:
    """A question the corpus answers comes back as prose with citations."""
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("Marcus put the rev B boards two weeks out, pending connectors."),
            answered(),
        ]
    )
    search = StubSearch(result=found())
    response = request(
        answering_app(model, search),
        "POST",
        "/answer",
        json={"question": "Where are the rev B boards?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Marcus put the rev B boards")
    assert body["searches"] == 1
    assert [row["document_slug"] for row in body["citations"]] == ["rev-b-schedule"]
    assert body["citations"][0]["location"] == "turns 0-1"
    assert body["thread_id"]
    assert [call["query"] for call in search.calls] == ["connector lead time"]
    # A question the corpus answered routes to nobody. There is nothing to
    # ask a colleague once the record has said it.
    assert body["routing"] is None


def test_abstains_when_the_corpus_does_not_answer() -> None:
    """A search that finds nothing is answered, not errored.

    The model is told so in as many words, and the response carries no
    citations because there was nothing to cite. That is the success state
    the system prompt names, so it is a 200 like any other answer.
    """
    model = ScriptedModel(
        [
            searches("kalamazoo office"),
            says("The record does not say anything about a Kalamazoo office."),
        ]
    )
    search = StubSearch(result=nothing())
    response = request(
        answering_app(model, search),
        "POST",
        "/answer",
        json={"question": "What is the Kalamazoo office working on?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert (
        body["answer"] == "The record does not say anything about a Kalamazoo office."
    )
    assert body["citations"] == []
    assert body["searches"] == 1
    # Nothing came back, so no passage named anybody, and a suggestion
    # naming nobody is not a suggestion.
    assert body["routing"] is None
    # The model was shown that the search came back empty, and which term
    # the corpus has never seen, rather than an empty string.
    shown = model.prompts[-1][-1].content
    assert 'No passages matched "kalamazoo office"' in shown
    assert "Nothing in the record contains: kalamazoo." in shown


def test_declines_an_out_of_scope_question_without_searching() -> None:
    """A question the corpus could not hold is declined, and nothing is searched."""
    model = ScriptedModel(
        [says("I answer from this organization's own record, and that is outside it.")]
    )
    search = StubSearch(result=found())
    response = request(
        answering_app(model, search),
        "POST",
        "/answer",
        json={"question": "What is the capital of France?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "outside it" in body["answer"]
    assert body["citations"] == []
    assert body["searches"] == 0
    assert body["routing"] is None
    assert search.calls == []
    # Judging an answer costs a second model call, and a question that was
    # never going to be in the record does not pay for one.
    assert len(model.prompts) == 1


def test_a_multi_part_question_searches_more_than_once() -> None:
    """Two tool calls are two searches, and both sets of passages are cited."""
    model = ScriptedModel(
        [
            searches("connector lead time", call_id="a"),
            searches("firmware freeze date", call_id="b"),
            says("The boards are two weeks out and the freeze holds."),
            answered(),
        ]
    )
    search = StubSearch(result=found())
    app = answering_app(model, search)

    # Both searches return the same passage, so the response also shows that
    # a passage two searches both found is cited once.
    response = request(
        app,
        "POST",
        "/answer",
        json={"question": "Where are the boards, and when is the firmware freeze?"},
    )

    body = response.json()
    assert body["searches"] == 2
    assert len(body["citations"]) == 1
    assert [call["query"] for call in search.calls] == [
        "connector lead time",
        "firmware freeze date",
    ]


def test_a_follow_up_continues_the_thread() -> None:
    """A second question on the same thread sees the first, and need not search."""
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("Two weeks out, pending connectors."),
            answered(),
            says("Marcus said it."),
        ]
    )
    search = StubSearch(result=found())
    app = answering_app(model, search)

    first, second = conversation(
        app,
        {"question": "Where are the rev B boards?"},
        {"question": "Who said that?", "_thread_from": 0},
    )

    assert second["thread_id"] == first["thread_id"]
    assert second["searches"] == 0
    assert second["citations"] == []
    assert len(search.calls) == 1
    # The follow-up was answered from a conversation that still held the
    # first question, its search, and its answer.
    assert len(model.prompts[-1]) > len(model.prompts[0])


def test_the_search_ceiling_makes_the_model_answer() -> None:
    """A model that keeps searching is eventually called without its tools.

    A small model can decide to search, read the passages, and decide to
    search again indefinitely. The ceiling turns that into an answer rather
    than a request that never returns.
    """
    model = ScriptedModel(
        [searches(f"round {index}", call_id=str(index)) for index in range(2)]
        + [says("Two weeks out."), answered()]
    )
    search = StubSearch(result=found())

    @asynccontextmanager
    async def open_scripted(app):
        """Open an agent that will only tolerate two searches."""
        client = in_process_client(app)
        try:
            yield Agent(
                graph=build_graph(
                    model,
                    [search_tool(client)],
                    checkpointer=InMemorySaver(),
                    max_searches=2,
                )
            )
        finally:
            await client.aclose()

    app = create_app(
        resources=lambda: Resources(
            connection=connect(":memory:"), collection=FakeCollection()
        ),
        search=search,
        agent=open_scripted,
    )
    body = request(
        app, "POST", "/answer", json={"question": "Where are the boards?"}
    ).json()

    assert body["searches"] == 2
    assert body["answer"] == "Two weeks out."
    # The last call was made without tools attached, which is what left the
    # model no move but to answer.
    assert model.with_tools == [True, True, False, False]


def test_an_empty_question_is_rejected() -> None:
    """A question that is only whitespace is a caller that lost its input."""
    response = request(
        answering_app(ScriptedModel([]), StubSearch(result=found())),
        "POST",
        "/answer",
        json={"question": "   "},
    )
    assert response.status_code == 422


def test_search_is_still_curlable() -> None:
    """Adding the agent did not change what ``/search`` returns."""
    response = request(
        answering_app(ScriptedModel([]), StubSearch(result=found())),
        "POST",
        "/search",
        json={"query": "connector lead time"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "connector lead time"
    assert body["results"][0]["document_slug"] == "rev-b-schedule"
    assert "confidence" in body


def test_the_tool_is_described_to_the_model_once() -> None:
    """The tool schema comes from the tool, and is attached by ``bind_tools``."""
    model = ScriptedModel([says("no")])
    search = StubSearch(result=found())
    request(
        answering_app(model, search),
        "POST",
        "/answer",
        json={"question": "anything"},
    )
    (tool,) = model.bound
    assert tool.name == TOOL_NAME
    assert "query" in tool.args_schema.model_json_schema()["properties"]


def test_passages_carry_where_they_came_from() -> None:
    """A passage is rendered with the document, date, and place behind it."""
    rendered = render_passages(
        "rev B boards",
        [
            {
                "title": "Rev B schedule",
                "document_date": "2026-03-04",
                "author": None,
                "location": "turns 0-1",
                "text": "Two weeks out.",
            }
        ],
    )
    assert rendered.endswith(
        "[1] Rev B schedule (2026-03-04, turns 0-1)\nTwo weeks out."
    )
    # The passages open with what was searched for and a reminder that
    # ranking is not relevance, which is the whole point of the header.
    assert rendered.startswith('The 1 closest passages to "rev B boards".')
    assert "Closest is not the same as relevant" in rendered


def test_an_authored_passage_names_its_author() -> None:
    """A document with an author shows it; a transcript has attendees instead."""
    rendered = render_passages(
        "connector tolerances",
        [
            {
                "title": "Connector spec",
                "document_date": "2026-02-01",
                "author": "Devon",
                "location": "Scope > Tolerances",
                "text": "0.2mm.",
            }
        ],
    )
    assert "(2026-02-01, Devon, Scope > Tolerances)" in rendered


def test_a_citation_drops_the_text_and_the_scores() -> None:
    """A citation says where to look, not what was read or how it ranked."""
    result = a_result()
    row = citation(
        {
            "chunk_id": result.chunk_id,
            "document_slug": result.document_slug,
            "source_kind": result.source_kind,
            "title": result.title,
            "document_date": result.document_date,
            "author": result.author,
            "attendees": result.attendees,
            "location": result.location,
            "text": result.text,
            "rerank_score": result.rerank_score,
        }
    )
    assert set(row) == {
        "chunk_id",
        "document_slug",
        "source_kind",
        "title",
        "document_date",
        "author",
        "attendees",
        "location",
    }


def test_an_abstention_suggests_who_to_ask() -> None:
    """A question the passages did not settle comes back with a routing.

    The passage that failed to answer the question is a meeting, and a
    meeting names who was in the room. Those are the people to ask.
    """
    draft = (
        "I was looking for what the rev B connector tolerance was set to, and "
        "the record covers the schedule for that board without naming a "
        "figure. What tolerance did we settle on?"
    )
    model = ScriptedModel(
        [
            searches("rev B connector tolerance"),
            says("The record does not give a tolerance for the rev B connector."),
            # The routing model answers in the two labelled lines its prompt
            # asks for; what the response carries is the prose inside them.
            says(
                "CONTEXT: I was looking for what the rev B connector tolerance "
                "was set to, and the record covers the schedule for that board "
                "without naming a figure.\n"
                "QUESTION: What tolerance did we settle on?"
            ),
        ]
    )
    search = StubSearch(result=found())
    body = request(
        answering_app(model, search),
        "POST",
        "/answer",
        json={"question": "What tolerance did we set on the rev B connector?"},
    ).json()

    routing = body["routing"]
    assert routing["question"] == draft
    # Everyone in the room, each with the passage that put them there.
    assert [person["name"] for person in routing["candidates"]] == [
        "Priya",
        "Marcus",
        "Sofia",
    ]
    priya = routing["candidates"][0]
    assert priya["role"] == "CEO"
    assert priya["department"] == "Executive"
    assert priya["passages"] == 1
    # The why cites the way an answer's claims cite.
    [evidence] = priya["evidence"]
    assert evidence["title"] == "Rev B schedule"
    assert evidence["document_slug"] == "rev-b-schedule"
    assert evidence["location"] == "turns 0-1"
    assert evidence["attendees"] == ["Priya", "Marcus", "Sofia"]
    assert evidence["author"] is None
    # The routing model was shown the question and the answer, and nothing
    # it said joined the conversation the user is having.
    judged = model.prompts[-1][-1].content
    assert "What tolerance did we set on the rev B connector?" in judged
    assert "The record does not give a tolerance" in judged


def test_routing_ranks_by_how_much_of_the_material_each_person_owns() -> None:
    """Whoever wrote or attended more of what matched is suggested first."""
    model = ScriptedModel(
        [
            searches("connector tolerance"),
            says("The record does not say what the tolerance was set to."),
            says("What tolerance did we settle on for the rev B connector?"),
        ]
    )
    search = StubSearch(
        result=all_of(
            a_result(rank=1, chunk_id=7, attendees=["Priya", "Marcus"]),
            a_result(
                rank=2,
                chunk_id=8,
                score=3.1,
                author="Marcus",
                document_slug="connector-spec",
                title="Connector spec",
                source_kind="docx",
                location="Scope > Tolerances",
            ),
        )
    )
    body = request(
        answering_app(model, search),
        "POST",
        "/answer",
        json={"question": "What tolerance did we set on the rev B connector?"},
    ).json()

    candidates = body["routing"]["candidates"]
    assert [person["name"] for person in candidates] == ["Marcus", "Priya"]
    marcus, priya = candidates
    assert marcus["passages"] == 2
    assert priya["passages"] == 1
    # Marcus's evidence is both the meeting he sat in and the document he
    # wrote, each cited where it is.
    assert [row["location"] for row in marcus["evidence"]] == [
        "turns 0-1",
        "Scope > Tolerances",
    ]
    assert marcus["evidence"][1]["author"] == "Marcus"


def test_a_name_the_roster_does_not_have_is_not_suggested() -> None:
    """A suggestion names a person, not a string out of a file's properties."""
    model = ScriptedModel(
        [
            searches("connector tolerance"),
            says("The record does not say."),
            says("What tolerance did we settle on?"),
        ]
    )
    search = StubSearch(
        result=found(author="wm-scanner-01", attendees=[], source_kind="docx")
    )
    body = request(
        answering_app(model, search),
        "POST",
        "/answer",
        json={"question": "What tolerance did we set on the rev B connector?"},
    ).json()

    assert body["routing"] is None


def test_a_failing_search_is_reported_not_narrated_around() -> None:
    """A search endpoint that refuses does not become an invented answer."""

    async def run() -> None:
        async def refuse(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "index is gone"})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(refuse), base_url="http://retrieval.test"
        )
        tool = search_tool(client)
        with pytest.raises(httpx.HTTPStatusError):
            await tool.coroutine(query="anything")
        await client.aclose()

    asyncio.run(run())
