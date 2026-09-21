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

What answering records is asserted here rather than in the API tests,
because whether a turn abstained is the graph's judgement and a gap is
written from it. The records go to a temporary usage database, as they do
for every test in the suite.

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
from corpus_query.agent.runtime import correction_recorder
from corpus_query.agent.retrieval import (
    TOOL_NAME,
    citation,
    in_process_client,
    render_passages,
    search_tool,
)
from corpus_query.api.app import Resources, create_app
from corpus_query.retrieval.search import Confidence, SearchResult
from corpus_query.store import capture
from corpus_query.store.db import connect
from test_api import (
    FakeCollection,
    StubSearch,
    a_confidence,
    a_result,
    captured_records,
    request,
)


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
    """The tools the first ``bind_tools`` call attached: the ones every
    question is offered."""
    bindings: list[list[Any]] = field(default_factory=list)
    """Every set of tools the graph attached, in the order it attached them."""
    with_tools: list[bool] = field(default_factory=list)
    """One entry per call: whether the tools were attached for it."""
    offered: list[list[str]] = field(default_factory=list)
    """One entry per call: the names of the tools attached for it."""

    def bind_tools(self, tools: list[Any]) -> BoundModel:
        """Record the tools and hand back the model they are attached to.

        Args:
            tools: What the graph attached.

        Returns:
            The same script, reached through a distinct object, so a test
            can tell a call made with tools from one made without.
        """
        if not self.bindings:
            self.bound = list(tools)
        self.bindings.append(list(tools))
        return BoundModel(self, [tool.name for tool in tools])

    async def ainvoke(self, messages: list[Any], **kwargs: Any) -> AIMessage:
        """Return the next scripted reply, for a call made without tools."""
        return self.next_reply(messages, tools=[])

    def next_reply(self, messages: list[Any], tools: list[str]) -> AIMessage:
        """Record one call and pop the reply that answers it.

        Args:
            messages: The conversation so far, system prompt included.
            tools: The names of the tools the caller had attached.

        Returns:
            The next message in the script.

        Raises:
            AssertionError: If the graph called the model more times than
                the script accounts for, which is a loop rather than a run.
        """
        self.prompts.append(list(messages))
        self.with_tools.append(bool(tools))
        self.offered.append(tools)
        if not self.replies:
            raise AssertionError("the graph called the model past its script")
        return self.replies.pop(0)


@dataclass
class BoundModel:
    """The scripted model with its tools attached."""

    model: ScriptedModel
    tools: list[str]

    async def ainvoke(self, messages: list[Any], **kwargs: Any) -> AIMessage:
        """Return the next scripted reply, for a call made with tools."""
        return self.model.next_reply(messages, tools=self.tools)


def says(text: str) -> AIMessage:
    """Build a model reply that answers and calls nothing."""
    return AIMessage(text)


def answered() -> AIMessage:
    """Build the routing model's reply for an answer that settled it."""
    return AIMessage("ANSWERED")


def verified() -> AIMessage:
    """Build the verification model's reply for a fully supported answer."""
    return AIMessage("VERIFIED")


def rejects(*claims: str) -> AIMessage:
    """Build the verification model's reply naming unsupported claims."""
    return AIMessage("\n".join(f"UNSUPPORTED: {claim}" for claim in claims))


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
        """Open the agent against the scripted model and an in-memory thread store.

        Corrections are written the way the service writes them, to the
        usage database the application's own records are in, so what the
        agent records and what ``/corrections`` reads back are the same
        rows.
        """
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

    return create_app(
        resources=lambda: Resources(
            connection=connect(":memory:"),
            collection=FakeCollection(),
            captured=captured_records(),
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


def answer_directly(app, question: str, thread_id: str | None = None) -> Any:
    """Ask the agent a question without going through the HTTP endpoint.

    ``/answer`` reports a fixed, published shape, and fields the rewrite and
    verification steps add — the resolved query, what verification found —
    are not part of it, and adding them is out of scope for this change. A
    test that wants to see one of those fields reaches the agent directly,
    the way :func:`corpus_query.agent.runtime.open_agent` opens it.

    Args:
        app: The application to open the agent against.
        question: The question to ask.
        thread_id: The conversation to continue, if any.

    Returns:
        The :class:`~corpus_query.agent.graph.Answer` the agent produced.
    """

    async def run() -> Any:
        async with app.router.lifespan_context(app):
            return await app.state.agent.answer(question, thread_id=thread_id)

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
            verified(),
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
            verified(),
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
            verified(),
            answered(),
            says("Who said the rev B boards were two weeks out?"),
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


def test_a_follow_up_is_resolved_before_it_searches() -> None:
    """A follow-up's standalone form is what actually reaches retrieval.

    "What about the refinery one?" means nothing to ``search_corpus`` on its
    own. The rewrite step is what turns it into something worth searching
    for before the model ever decides what to search — this drives that
    through the real graph and checks what was actually posted to
    ``/search``.
    """
    resolved = "What did the refinery review decide about the compressor?"
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("Two weeks out, pending connectors."),
            verified(),
            answered(),
            # The rewrite model's reply for the second question.
            says(resolved),
            searches(resolved, call_id="b"),
            says("The refinery review approved the compressor spec."),
            verified(),
            answered(),
        ]
    )
    search = StubSearch(result=found())
    app = answering_app(model, search)

    first, second = conversation(
        app,
        {"question": "Where are the rev B boards?"},
        {"question": "What about the refinery one?", "_thread_from": 0},
    )

    assert search.calls[0]["query"] == "connector lead time"
    # The follow-up itself was never posted to /search; its resolved form
    # was.
    assert search.calls[-1]["query"] == resolved
    assert "What about the refinery one?" not in [
        call["query"] for call in search.calls
    ]
    assert second["answer"] == "The refinery review approved the compressor spec."


def test_the_resolved_query_is_recorded_even_when_unchanged() -> None:
    """A question with nothing to resolve is recorded as itself.

    The first question on a thread has no earlier conversation to rewrite
    against, so it costs no extra model call — this is the case, not the
    exception, since most threads open with a standalone question.
    """
    model = ScriptedModel([says("Two weeks out.")])
    app = answering_app(model, StubSearch(result=found()))

    answer = answer_directly(app, "Where are the rev B boards?")

    assert answer.resolved_query == "Where are the rev B boards?"
    # Nothing was searched or drafted for this question, so nothing was
    # verified either.
    assert answer.verification is None
    # No rewrite call was spent on a question that had nothing to resolve.
    assert len(model.prompts) == 1


def test_an_unsupported_claim_sends_the_answer_back_for_a_redraft() -> None:
    """A citation that does not support its claim triggers a redraft.

    The first draft states something the passages never said. Verification
    catches it and the model is asked again; the redraft is what the caller
    actually sees.
    """
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("Marcus said the freeze moved to March 19th."),
            rejects("Marcus said the freeze moved to March 19th."),
            says("Two weeks out, pending connectors."),
            verified(),
            answered(),
        ]
    )
    app = answering_app(model, StubSearch(result=found()))

    answer = answer_directly(app, "Where are the rev B boards?")

    assert answer.answer == "Two weeks out, pending connectors."
    assert answer.verification is None


def test_regeneration_stops_at_the_bound_and_says_so() -> None:
    """A claim that keeps failing does not loop forever.

    Past the bound, the last draft is returned as it stands rather than
    being redrafted again, and the caller is told outright that
    verification never cleared it — the deliberate, documented behavior the
    bound exists for.
    """
    claim = "Marcus said the freeze moved to March 19th."
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says(claim),
            rejects(claim),
            says(claim),
            rejects(claim),
            says(claim),
            rejects(claim),
            answered(),
        ]
    )
    app = answering_app(model, StubSearch(result=found()))

    answer = answer_directly(app, "Where are the rev B boards?")

    assert answer.answer == claim
    assert answer.verification == {"rejected": [claim], "exhausted": True}


def test_an_unreadable_verify_reply_is_recorded_without_a_redraft() -> None:
    """A verify reply with no labelled line is not treated as a rejection.

    A small model sometimes answers verification by echoing the drafted
    answer back instead of writing the sentinel or a labelled line. That is
    not evidence anything was rejected, and asking the model to redraft
    over it cannot converge — see ``verification.py``. It costs no redraft
    and no regeneration attempt; the draft is returned as it stands and the
    reply that could not be read is kept on the answer.
    """
    draft = "Marcus said the freeze moved to March 19th."
    echo = (
        "The record indicates that Marcus said the freeze moved to March "
        "19th, as shown in the passage."
    )
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says(draft),
            AIMessage(echo),
            answered(),
        ]
    )
    app = answering_app(model, StubSearch(result=found()))

    answer = answer_directly(app, "Where are the rev B boards?")

    assert answer.answer == draft
    assert answer.verification == {"unreadable": True, "reply": echo}
    # The script had exactly one draft, one verify call, and one route
    # call after the search; a redraft would have needed a reply the
    # script does not have, and ScriptedModel raises if the graph asks for
    # one past the end of its script.
    assert len(model.prompts) == 4


def test_the_search_ceiling_makes_the_model_answer() -> None:
    """A model that keeps searching is eventually called without its tools.

    A small model can decide to search, read the passages, and decide to
    search again indefinitely. The ceiling turns that into an answer rather
    than a request that never returns.
    """
    model = ScriptedModel(
        [searches(f"round {index}", call_id=str(index)) for index in range(2)]
        + [says("Two weeks out."), verified(), answered()]
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
            connection=connect(":memory:"),
            collection=FakeCollection(),
            captured=captured_records(),
        ),
        search=search,
        agent=open_scripted,
    )
    body = request(
        app, "POST", "/answer", json={"question": "Where are the boards?"}
    ).json()

    assert body["searches"] == 2
    assert body["answer"] == "Two weeks out."
    # The last two calls were made without tools attached: one is the model
    # being made to answer once the ceiling was hit, the other is
    # verification, which never gets tools.
    assert model.with_tools == [True, True, False, False, False]


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
            verified(),
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
            verified(),
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
            verified(),
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


def recorded():
    """Read back what answering wrote to the usage database.

    The application records into the project's default usage database,
    which the suite points at a temporary file for every test, so this
    opens the same file the request just wrote to.

    Returns:
        The answers, gaps, and corrections in it.
    """
    connection = capture.connect()
    try:
        return {
            "answers": connection.execute(
                "SELECT * FROM answers ORDER BY rowid"
            ).fetchall(),
            "gaps": capture.gaps(connection),
            "corrections": capture.corrections(connection),
        }
    finally:
        connection.close()


def test_an_answered_question_is_recorded_and_is_not_a_gap() -> None:
    """One row per question, with the id the caller needs to correct it."""
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("Marcus put the rev B boards two weeks out."),
            verified(),
            answered(),
        ]
    )
    body = request(
        answering_app(model, StubSearch(result=found())),
        "POST",
        "/answer",
        json={"question": "Where are the rev B boards?"},
    ).json()

    written = recorded()
    [answer] = written["answers"]
    assert body["answer_id"] == answer["id"]
    assert answer["query"] == "Where are the rev B boards?"
    assert answer["answer"] == "Marcus put the rev B boards two weeks out."
    assert answer["thread_id"] == body["thread_id"]
    assert answer["abstained"] == 0
    assert "rev-b-schedule" in answer["citations"]
    assert answer["created_at"]
    # The record settled the question, so there is nothing missing from it.
    assert written["gaps"] == []


def test_an_abstention_records_a_gap_carrying_the_suggestion() -> None:
    """A gap is detected rather than reported, and keeps what was suggested."""
    model = ScriptedModel(
        [
            searches("rev B connector tolerance"),
            says("The record does not give a tolerance for the rev B connector."),
            verified(),
            says(
                "CONTEXT: The record covers the schedule without naming a "
                "figure.\nQUESTION: What tolerance did we settle on?"
            ),
        ]
    )
    body = request(
        answering_app(model, StubSearch(result=found())),
        "POST",
        "/answer",
        json={"question": "What tolerance did we set on the rev B connector?"},
    ).json()

    written = recorded()
    [answer] = written["answers"]
    [gap] = written["gaps"]
    assert answer["abstained"] == 1
    assert gap["answer_id"] == body["answer_id"]
    assert gap["question"] == "What tolerance did we set on the rev B connector?"
    # The suggestion is stored as it was made, rather than rebuilt later
    # against a roster and a corpus that have both moved on.
    assert gap["routing"] == body["routing"]
    assert [person["name"] for person in gap["routing"]["candidates"]] == [
        "Priya",
        "Marcus",
        "Sofia",
    ]


def test_a_search_that_found_nothing_is_a_gap_without_a_suggestion() -> None:
    """Nothing came back, so nobody was named, and the gap is recorded anyway."""
    model = ScriptedModel(
        [
            searches("kalamazoo office"),
            says("The record does not say anything about a Kalamazoo office."),
        ]
    )
    request(
        answering_app(model, StubSearch(result=nothing())),
        "POST",
        "/answer",
        json={"question": "What is the Kalamazoo office working on?"},
    )

    written = recorded()
    [answer] = written["answers"]
    [gap] = written["gaps"]
    assert answer["abstained"] == 1
    assert gap["routing"] is None
    assert gap["question"] == "What is the Kalamazoo office working on?"


def test_an_abstention_naming_nobody_is_still_a_gap() -> None:
    """The passages named no colleague, which costs the suggestion, not the gap."""
    model = ScriptedModel(
        [
            searches("connector tolerance"),
            says("The record does not say."),
            verified(),
            says("What tolerance did we settle on?"),
        ]
    )
    body = request(
        answering_app(
            model,
            StubSearch(
                result=found(author="wm-scanner-01", attendees=[], source_kind="docx")
            ),
        ),
        "POST",
        "/answer",
        json={"question": "What tolerance did we set on the rev B connector?"},
    ).json()

    written = recorded()
    [gap] = written["gaps"]
    assert body["routing"] is None
    assert gap["routing"] is None
    assert written["answers"][0]["abstained"] == 1


def test_an_out_of_scope_question_is_recorded_but_is_not_a_gap() -> None:
    """A question this record was never going to hold is not missing from it."""
    model = ScriptedModel(
        [says("I answer from this organization's own record, and that is outside it.")]
    )
    request(
        answering_app(model, StubSearch(result=found())),
        "POST",
        "/answer",
        json={"question": "What is the capital of France?"},
    )

    written = recorded()
    [answer] = written["answers"]
    assert answer["abstained"] == 0
    assert answer["query"] == "What is the capital of France?"
    assert written["gaps"] == []


def test_a_correction_can_name_the_answer_that_came_back() -> None:
    """The id the response carries is the id a correction is written against.

    This is the whole point of the answer row: a correction typed later
    names an answer rather than a question string that may have been asked
    more than once.
    """
    model = ScriptedModel(
        [
            searches("connector lead time"),
            says("The freeze is March 12th."),
            verified(),
            answered(),
        ]
    )
    app = answering_app(model, StubSearch(result=found()))

    [asked] = conversation(app, {"question": "When is the firmware freeze?"})
    response = request(
        app,
        "POST",
        "/corrections",
        json={
            "answer_id": asked["answer_id"],
            "what_was_wrong": "It said the freeze is March 12th.",
            "what_is_right": "The freeze moved to March 19th.",
        },
    )

    assert response.status_code == 201
    assert response.json()["question"] == "When is the firmware freeze?"
