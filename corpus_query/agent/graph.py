"""The graph: a rewrite, a model that may search, the loop around it, a
verification pass, and what to do when the search did not settle the
question.

Five nodes. ``rewrite`` turns the newest turn into a question that stands on
its own, before anything searches, since a follow-up like "what about the
refinery one?" is only that specific once the rest of the conversation is
read alongside it. ``think`` calls the model. ``tools`` runs whatever the
model asked for and feeds the results back. The edge between them is
conditional, so a question the model answers outright never reaches
retrieval at all, and a question with two halves goes round twice. That loop
is most of the reason the agent exists as a graph rather than a function
that searches and then summarizes.

``verify`` runs once the model has stopped calling tools and has drafted an
answer that cites something. It re-checks each of the answer's claims
against the passages that were searched for, and when a claim is not there,
sends the model back to ``think`` for another draft — bounded, so a claim the
model cannot stop making is eventually returned as-is rather than chased
forever; see :data:`MAX_REGENERATIONS`.

``route`` runs after verification has settled, and does something only for a
turn that searched. It asks whether the answer settled the question, and
when it did not, turns the passages that failed to answer it into a
suggestion of who to ask. Its model call is its own, like verification's:
neither the prompt nor the reply joins the conversation, because a drafted
question or a verification note appended to the history is something the
next turn would try to answer or re-litigate.

The model is passed in. Nothing here imports a provider, names one, or knows
what is answering — tools are attached with ``bind_tools``, so the tool schema
is written once and translated by whichever chat model receives it.

The system prompt is prepended at each model call rather than stored in the
graph's state. State is checkpointed and replayed, and a prompt that lives in
it is a prompt that gets frozen into every thread ever started, so editing the
file would change new conversations and not resumed ones.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from corpus_query.agent.prompts import load
from corpus_query.agent.rewriting import resolved_query as read_rewrite
from corpus_query.agent.routing import drafted_question, suggestion
from corpus_query.agent.verification import read_verdict

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.checkpoint.base import BaseCheckpointSaver

#: How many times one question may reach retrieval before the model is made
#: to answer with what it has. Multi-part questions are meant to search more
#: than once, so the ceiling is well above the two or three a real question
#: takes; it is here because a small model that has decided to search can
#: decide it again indefinitely, and a request that never returns is worse
#: than one that answers from four searches.
MAX_SEARCHES = 6

#: How many redrafts one turn may go through when verification keeps
#: rejecting a claim, on top of the first draft. Real unsupported claims are
#: usually gone after one redraft with the rejection named; a claim that
#: survives this many redrafts is treated as this model's ceiling rather
#: than chased indefinitely, and what happens instead is deliberate: the
#: last draft is returned as it stands, and :data:`Answer.verification`
#: says outright that it was not cleared, rather than the turn either
#: looping or silently keeping a claim nobody checked.
MAX_REGENERATIONS = 2


@dataclass(frozen=True)
class Answer:
    """One answered question."""

    answer: str
    """The prose the model wrote. An abstention is a normal value here."""

    citations: list[dict[str, Any]]
    """The passages this turn's searches returned, best first, deduplicated.
    Empty when the model answered without searching — which an out-of-scope
    decline does, and so does a question the conversation already covered."""

    searches: int
    """How many searches this turn ran."""

    routing: dict[str, Any] | None
    """Who to ask, when the turn searched and the answer did not settle the
    question: candidates, the passages that named each of them, and a
    drafted question. ``None`` for an answered question, for one declined
    without a search, and for one whose passages name nobody on the
    roster."""

    abstained: bool
    """Whether the record failed to settle the question. True when the turn
    searched and the answer did not settle what was asked, which includes
    the search that came back empty and the one whose passages named nobody
    to route to. False for an answered question, and false for one declined
    without a search — a question this organization was never going to be
    asked is out of scope rather than a gap in its record."""

    thread_id: str
    """The conversation this turn belongs to. Passing it back continues the
    conversation; leaving it out starts a new one."""

    resolved_query: str
    """The question this turn actually searched from: the raw question,
    rewritten to stand on its own when there was earlier conversation to
    resolve it against, and the raw question unchanged otherwise. Recorded
    because a mangled rewrite is the first suspect when retrieval quality
    drops on a follow-up, and this is what settles whether that is what
    happened."""

    verification: dict[str, Any] | None
    """What citation verification found, or ``None`` when the turn drafted
    nothing to verify or every claim it made was supported on the first
    pass. Otherwise one of two shapes. When the model named specific
    unsupported claims: ``rejected``, those claims from the last check, and
    ``exhausted``, whether that check ran out of redrafts to try — see
    :data:`MAX_REGENERATIONS`. When the model's reply was neither the
    sentinel nor a single labelled rejection — a shape verification cannot
    act on: ``unreadable`` (``True``) and ``reply``, what the model actually
    said. An unreadable reply is not redrafted, since a redraft cannot
    converge on a check that never named anything to fix. The answer itself
    is always the last draft produced, whether or not verification ever
    cleared it."""


@dataclass(frozen=True)
class Agent:
    """A compiled graph and the conversation it is invoked through."""

    graph: Any
    """The compiled LangGraph graph. Compiled once, awaited per request."""

    system_prompt: str = field(default_factory=lambda: load("answer"))

    routing_prompt: str = field(default_factory=lambda: load("route"))
    """What the routing node judges an answer with. Held here for the same
    reason the system prompt is: it travels as state rather than being read
    inside the node, so editing the file changes resumed conversations as
    well as new ones."""

    rewrite_prompt: str = field(default_factory=lambda: load("rewrite"))
    """What the rewrite node expands a turn's question with. Held here for
    the same reason the other prompts are."""

    verify_prompt: str = field(default_factory=lambda: load("verify"))
    """What the verify node checks a drafted answer's claims with. Held here
    for the same reason the other prompts are."""

    async def answer(self, question: str, thread_id: str | None = None) -> Answer:
        """Answer one question.

        The same run :meth:`stream` makes, with the progress along the way
        dropped, so the two can never disagree about what the answer is.

        Args:
            question: The question, in natural language.
            thread_id: The conversation to continue. A new one is started
                when this is not given.

        Returns:
            The answer, its citations, and the conversation it belongs to.
        """
        result: Answer | None = None
        async for item in self.stream(question, thread_id=thread_id):
            if isinstance(item, Answer):
                result = item
        if result is None:  # pragma: no cover - stream always ends on one
            raise RuntimeError("the graph finished without an answer")
        return result

    async def stream(
        self, question: str, thread_id: str | None = None
    ) -> AsyncIterator[Progress | Answer]:
        """Answer one question, reporting each step as it happens.

        The graph is run with LangGraph's task stream, which reports a node
        as it starts and again when it finishes, and each of those that
        means something to a person waiting is turned into a
        :class:`Progress`. What each event means is set out in
        :data:`EVENTS`.

        A run that is abandoned partway — the caller stopped listening, the
        model failed, the process was stopped — leaves its thread holding
        half a turn. The next question asked on that thread clears it first;
        see :meth:`_abandoned`.

        Args:
            question: The question, in natural language.
            thread_id: The conversation to continue. A new one is started
                when this is not given.

        Yields:
            :class:`Progress` for each step, in the order the graph took
            them, and then the :class:`Answer`, last.
        """
        thread = thread_id or uuid.uuid4().hex
        config = {"configurable": {"thread_id": thread}}
        yield Progress("started", {"thread_id": thread})
        cleared = await self._abandoned(config) if thread_id else []
        turn_input = {
            "messages": [*cleared, HumanMessage(question)],
            "system_prompt": self.system_prompt,
            "routing_prompt": self.routing_prompt,
            "rewrite_prompt": self.rewrite_prompt,
            "verify_prompt": self.verify_prompt,
            # Cleared on the way in. State outlives a turn, so a
            # suggestion, a rewrite, or a verification left over from an
            # earlier question would otherwise come back attached to the
            # answer to this one.
            "routing": None,
            "abstained": False,
            "resolved_query": "",
            "verification": None,
            "verify_attempts": 0,
        }
        watch = _Watch()
        state: dict[str, Any] = {}
        async for mode, chunk in self.graph.astream(
            turn_input, config=config, stream_mode=["tasks", "values"]
        ):
            if mode == "values":
                state = chunk
                continue
            for progress in watch.saw(chunk):
                yield progress
        turn = _this_turn(state["messages"])
        yield Answer(
            answer=_final_text(turn),
            citations=_citations(turn),
            searches=sum(isinstance(message, ToolMessage) for message in turn),
            routing=state.get("routing"),
            abstained=bool(state.get("abstained")),
            thread_id=thread,
            resolved_query=state.get("resolved_query") or question,
            verification=state.get("verification"),
        )

    async def _abandoned(self, config: dict[str, Any]) -> list[RemoveMessage]:
        """Find what an unfinished run left on this thread, to clear it.

        Every step is checkpointed as it completes, so a run that stops
        partway leaves the thread holding the question and whatever the
        graph had done with it so far — which can be a search the model
        asked for with no result after it. That history is worse than none:
        the next turn's rewrite reads it as conversation, and a model
        provider that insists every tool call be answered refuses the
        thread outright. Nothing answered that question and nothing
        recorded it, so the turn is removed as if it had never been asked.

        A run is unfinished when the checkpoint still names nodes to run.
        Nothing in this graph pauses on purpose, so that only happens when a
        run was stopped; a task that did pause on purpose, with an
        interrupt, is left alone.

        Args:
            config: The thread, as the graph is invoked with it.

        Returns:
            One removal per message of the unfinished turn, to send in with
            the next question. Empty when the thread finished cleanly, is
            new, or is not persisted at all.
        """
        if self.graph.checkpointer is None:
            return []
        snapshot = await self.graph.aget_state(config)
        if not snapshot.next or any(task.interrupts for task in snapshot.tasks):
            return []
        turn = _this_turn(snapshot.values.get("messages", []))
        return [RemoveMessage(id=message.id) for message in turn]


#: What :meth:`Agent.stream` reports, in the order a searching turn reports
#: it. Each event's data is a JSON object.
EVENTS: dict[str, str] = {
    "started": "The question was received. ``thread_id`` is the conversation "
    "it belongs to, known before anything else has run.",
    "drafting": "The model has been asked to answer. It may ask for a search "
    "instead, in which case ``searching`` follows; after a search, or a "
    "rejected draft, this comes round again.",
    "searching": "Retrieval has started. ``query`` is what the model asked "
    "to search for.",
    "searched": "Retrieval returned. ``query`` is what was searched for and "
    "``citations`` the passages that came back, best first, in the shape "
    "an answer cites them in.",
    "verifying": "The drafted answer's claims are being checked against the "
    "passages that were searched for. A turn that cited nothing skips this.",
    "verified": "The check finished. ``verification`` is what it found, in "
    "the shape the answer records it in — null when every claim held up — "
    "and ``redraft`` is whether the model is being sent back to draft "
    "again.",
    "routing": "The answer is being judged against the question, to decide "
    "whether it settled it and who to ask if not. A turn that cited "
    "nothing skips this.",
}


@dataclass(frozen=True)
class Progress:
    """One step of a question being answered, as it happens."""

    event: str
    """Which step: one of :data:`EVENTS`."""

    data: dict[str, Any]
    """What the step has to say, as a JSON object."""


@dataclass
class _Watch:
    """Turns the graph's task stream into progress, one turn's worth.

    The task stream reports a node when it starts and again when it
    finishes, with what it wrote. A start is when a step begins; a finish
    is when there is something to say about what it found. The two need a
    little memory between them: a search result names only the call it
    answers, not what was searched for, and whether verification and
    routing do anything depends on whether a search returned passages.
    """

    queries: dict[str, str] = field(default_factory=dict)
    """What each tool call asked to search for, by call id."""

    cited: bool = False
    """Whether any search this turn returned a passage."""

    def saw(self, task: dict[str, Any]) -> list[Progress]:
        """Report what one task event means.

        Args:
            task: One item of LangGraph's ``tasks`` stream: a start carries
                ``input``, a finish carries ``result`` and ``error``.

        Returns:
            The progress to report for it, often none.
        """
        name = task["name"]
        if "result" not in task:
            if name == "think":
                return [Progress("drafting", {})]
            if name == "verify" and self.cited:
                return [Progress("verifying", {})]
            if name == "route" and self.cited:
                return [Progress("routing", {})]
            return []
        # A task that failed has nothing to report. The failure itself
        # comes out of the stream as an exception.
        if task.get("error") is not None:
            return []
        messages = (task["result"] or {}).get("messages", [])
        if name == "think":
            return self._searching(messages)
        if name == "tools":
            return self._searched(messages)
        if name == "verify" and self.cited:
            verification = task["result"].get("verification")
            return [
                Progress(
                    "verified",
                    {
                        "verification": verification,
                        "redraft": _needs_redraft(verification),
                    },
                )
            ]
        return []

    def _searching(self, messages: list[Any]) -> list[Progress]:
        """Report each search the model just asked for."""
        progress = []
        for message in messages:
            for call in getattr(message, "tool_calls", None) or []:
                query = str(call.get("args", {}).get("query", ""))
                self.queries[call.get("id") or ""] = query
                progress.append(Progress("searching", {"query": query}))
        return progress

    def _searched(self, messages: list[Any]) -> list[Progress]:
        """Report what each search that just ran came back with."""
        progress = []
        for message in messages:
            if not isinstance(message, ToolMessage):
                continue
            citations = list(message.artifact or [])
            self.cited = self.cited or bool(citations)
            progress.append(
                Progress(
                    "searched",
                    {
                        "query": self.queries.get(message.tool_call_id, ""),
                        "citations": citations,
                    },
                )
            )
        return progress


def _needs_redraft(verification: dict[str, Any] | None) -> bool:
    """Return whether a verification outcome sends the model back to draft.

    Args:
        verification: What ``verify`` recorded.

    Returns:
        True only when specific claims were rejected and redrafts remain.
        A verification with no ``"exhausted"`` key — the unreadable case —
        counts as done rather than redrafted, for the same reason ``verify``
        never appends a redraft request for it.
    """
    return verification is not None and not verification.get("exhausted", True)


class State(MessagesState):
    """The graph's state: the conversation, and the prompt above it.

    The prompt travels as state so that the node reading it does not reach
    back into the object that built the graph, which keeps the node a
    function of its input and lets a test run the graph with a prompt of its
    own.
    """

    system_prompt: str
    routing_prompt: str
    rewrite_prompt: str
    verify_prompt: str
    routing: dict[str, Any] | None
    abstained: bool
    resolved_query: str
    verification: dict[str, Any] | None
    verify_attempts: int


def build_graph(
    model: BaseChatModel,
    tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver | None = None,
    max_searches: int = MAX_SEARCHES,
    max_regenerations: int = MAX_REGENERATIONS,
) -> Any:
    """Compile the agent's graph.

    Called once, at startup. Compiling is not free and the result is
    stateless — every conversation it holds lives in the checkpointer, keyed
    by thread — so there is nothing a per-request compile would buy.

    Args:
        model: The chat model to answer with.
        tools: What the model may call. Attached with ``bind_tools``, so
            the schema the model is shown is generated from the tools
            themselves.
        checkpointer: Where to persist graph state between steps. None
            leaves the graph unpersisted, which is only what a test wants.
        max_searches: How many tool results one turn may accumulate before
            the model is called without tools and has to answer.
        max_regenerations: How many redrafts one turn may go through when
            verification keeps rejecting a claim. See
            :data:`MAX_REGENERATIONS`.

    Returns:
        The compiled graph.
    """
    with_tools = model.bind_tools(tools)

    async def rewrite(state: State) -> dict[str, str]:
        """Expand the newest turn into a question that stands on its own.

        A turn with no conversation before it has nothing to resolve, so
        that case is answered without a model call: the question is already
        standalone by construction. Every other turn is rewritten, since
        whether a follow-up needed resolving is exactly what a small model
        that skipped this step would get wrong.

        Args:
            state: The conversation, with the newest turn at the end.

        Returns:
            The standalone form of this turn's question, to record and for
            ``think`` to search from.
        """
        turn = _this_turn(state["messages"])
        question = _question(turn)
        history = state["messages"][: len(state["messages"]) - len(turn)]
        if not history:
            return {"resolved_query": question}
        reply = await model.ainvoke(
            [
                SystemMessage(state["rewrite_prompt"]),
                *history,
                HumanMessage(f"Newest question: {question}"),
            ]
        )
        return {"resolved_query": read_rewrite(_text_of(reply), fallback=question)}

    async def think(state: State) -> dict[str, list[AIMessage]]:
        """Call the model on the conversation so far.

        Args:
            state: The conversation and the system prompt above it.

        Returns:
            The model's reply, to append to the conversation.
        """
        system = state["system_prompt"]
        resolved = state.get("resolved_query") or ""
        if resolved and resolved != _question(_this_turn(state["messages"])):
            system = (
                f"{system}\n\nThis turn's question, resolved to stand on its "
                f"own: {resolved}"
            )
        messages = [SystemMessage(system), *state["messages"]]
        searches = sum(
            isinstance(message, ToolMessage)
            for message in _this_turn(state["messages"])
        )
        # Past the ceiling the model is called without its tools, so the
        # only move left is to answer. Refusing the tool call outright would
        # leave a dangling call in the history, which the next replay would
        # have to explain away.
        speaker = model if searches >= max_searches else with_tools
        return {"messages": [await speaker.ainvoke(messages)]}

    async def verify(state: State) -> dict[str, Any]:
        """Re-check the drafted answer's claims against what was searched.

        A turn that cited nothing has nothing to check — the out-of-scope
        decline and the answer taken straight from earlier conversation
        both skip the model call the same way ``route`` skips its own.

        Past :data:`max_regenerations` redrafts, a claim that is still
        rejected is left in the answer rather than redrafted again: the
        last draft is what ``route`` and the caller see, and
        ``state["verification"]`` says the check did not clear it.

        A reply this module cannot read as either the sentinel or a
        labelled rejection is not redrafted either — a reply outside that
        shape is not evidence a claim was rejected, and asking the model to
        redraft over it cannot converge on a check that never named
        anything to fix. ``state["verification"]`` records that the check
        could not be read, and the draft stands as it is.

        Args:
            state: The conversation, with the drafted answer at the end.

        Returns:
            Nothing, when there was nothing to verify or every claim held
            up. Otherwise the verification outcome, and — when redrafts
            remain because specific claims were rejected — a note appended
            to the conversation asking the model to draft again.
        """
        turn = _this_turn(state["messages"])
        if not _citations(turn):
            return {}
        passages = _passages_text(turn)
        judgement = await model.ainvoke(
            [
                SystemMessage(state["verify_prompt"]),
                HumanMessage(
                    f"Passages:\n{passages}\n\nDrafted answer:\n{_final_text(turn)}"
                ),
            ]
        )
        reply = _text_of(judgement)
        verdict = read_verdict(reply)
        if not verdict.rejected:
            if verdict.readable:
                return {"verification": None}
            return {"verification": {"unreadable": True, "reply": _truncated(reply)}}
        attempts = state.get("verify_attempts", 0)
        if attempts >= max_regenerations:
            return {"verification": {"rejected": verdict.rejected, "exhausted": True}}
        return {
            "messages": [SystemMessage(_regeneration_note(verdict.rejected))],
            "verification": {"rejected": verdict.rejected, "exhausted": False},
            "verify_attempts": attempts + 1,
        }

    async def route(state: State) -> dict[str, Any]:
        """Suggest who to ask, if the answer did not settle the question.

        The model judges its own answer, without its tools and without the
        conversation: it is shown the question and the answer, which is all
        that deciding between "this was answered" and "this was not" takes,
        and a prompt that short is what keeps a second call on every
        searching turn affordable.

        A turn that ran no search skips the call entirely. That is the
        out-of-scope decline: nothing was retrieved, so no passage named
        anybody, and routing is for questions this organization should be
        able to answer rather than for questions it was never going to be
        asked.

        The same call says whether the turn abstained, since deciding that
        is the question it was asked. A turn that searched and got nothing
        back needs no call to know: nothing came back to cite, so the
        record did not settle the question.

        Args:
            state: The conversation and the prompts above it.

        Returns:
            The routing to attach to this turn, or ``None``, and whether
            the turn abstained.
        """
        turn = _this_turn(state["messages"])
        citations = _citations(turn)
        if not citations:
            return {"routing": None, "abstained": _searched(turn)}
        judgement = await model.ainvoke(
            [
                SystemMessage(state["routing_prompt"]),
                HumanMessage(
                    f"Question asked:\n{_question(turn)}\n\n"
                    f"Answer given:\n{_final_text(turn)}"
                ),
            ]
        )
        reply = _text_of(judgement)
        # A suggestion is None both for an answer that settled the question
        # and for one that did not while naming nobody on the roster, so
        # whether the turn abstained is read from the reply rather than
        # from whether there was anyone to suggest.
        return {
            "routing": suggestion(citations, reply),
            "abstained": drafted_question(reply) is not None,
        }

    def after_verify(state: State) -> str:
        """Decide whether a verified turn is done or needs another draft.

        Args:
            state: The conversation and the verification just performed.

        Returns:
            ``"think"`` when verification appended a redraft request,
            ``"route"`` otherwise — a pass, nothing to verify, an
            unreadable reply, or the regeneration bound was reached. See
            :func:`_needs_redraft`.
        """
        return "think" if _needs_redraft(state.get("verification")) else "route"

    builder = StateGraph(State)
    builder.add_node("rewrite", rewrite)
    builder.add_node("think", think)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("verify", verify)
    builder.add_node("route", route)
    builder.add_edge(START, "rewrite")
    builder.add_edge("rewrite", "think")
    builder.add_conditional_edges(
        "think", tools_condition, {"tools": "tools", END: "verify"}
    )
    builder.add_edge("tools", "think")
    builder.add_conditional_edges(
        "verify", after_verify, {"think": "think", "route": "route"}
    )
    builder.add_edge("route", END)
    return builder.compile(checkpointer=checkpointer)


def _this_turn(messages: list[Any]) -> list[Any]:
    """Return the messages from the current question onward.

    A thread that has been asked three questions carries all three. What a
    response cites, and what the search ceiling counts, is this question's
    work alone.

    Args:
        messages: The whole conversation.

    Returns:
        Everything from the last question the user asked.
    """
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return messages[index:]
    return messages


def _searched(messages: list[Any]) -> bool:
    """Return whether this turn reached retrieval at all.

    Args:
        messages: This turn's messages.

    Returns:
        Whether any search ran.
    """
    return any(isinstance(message, ToolMessage) for message in messages)


def _question(messages: list[Any]) -> str:
    """Return the question this turn was asked.

    Args:
        messages: This turn's messages, which open with it.

    Returns:
        The question, or an empty string if the turn does not open with
        one.
    """
    for message in messages:
        if isinstance(message, HumanMessage):
            return _text_of(message)
    return ""


def _final_text(messages: list[Any]) -> str:
    """Return the text of the last thing the model said.

    Args:
        messages: This turn's messages.

    Returns:
        The answer, or an empty string if the model said nothing at all.
    """
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _text_of(message)
    return ""


def _text_of(message: Any) -> str:
    """Return one message's text.

    Args:
        message: The message to read.

    Returns:
        Its text, which is a string on every model that answers in prose
        and is coerced to one otherwise.
    """
    text = message.text
    return text if isinstance(text, str) else str(text)


def _citations(messages: list[Any]) -> list[dict[str, Any]]:
    """Collect the citations this turn's searches produced.

    Args:
        messages: This turn's messages.

    Returns:
        The cited passages in the order they were returned, with a passage
        that two searches both found appearing once.
    """
    collected: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for message in messages:
        if not isinstance(message, ToolMessage) or not message.artifact:
            continue
        for entry in message.artifact:
            if entry["chunk_id"] in seen:
                continue
            seen.add(entry["chunk_id"])
            collected.append(entry)
    return collected


def _passages_text(messages: list[Any]) -> str:
    """Collect the rendered passage text this turn's searches produced.

    This is what the model itself read before drafting — the same blocks
    :func:`corpus_query.agent.retrieval.render_passages` built, document and
    date and all — rather than the citations, which drop the text a claim
    would be checked against.

    Args:
        messages: This turn's messages.

    Returns:
        Every search's rendered results, in the order they were run,
        joined into one block. Empty when nothing was searched.
    """
    return "\n\n".join(
        message.content
        for message in messages
        if isinstance(message, ToolMessage) and isinstance(message.content, str)
    )


def _regeneration_note(rejected: list[str]) -> str:
    """Write the message that sends a rejected draft back for another one.

    Args:
        rejected: The claims verification found no passage supporting.

    Returns:
        An instruction to append to the conversation, naming exactly what
        was rejected rather than asking for a redraft in the abstract.
    """
    listed = "\n".join(f"- {claim}" for claim in rejected)
    return (
        "The passages above do not support at least one claim in the answer "
        f"you just gave:\n{listed}\n"
        "Write the answer again, using only what the passages actually say. "
        "Drop or soften anything they do not support; if that leaves nothing "
        "left to answer with, say the record does not say."
    )


#: How much of an unreadable verification reply to keep in
#: :data:`Answer.verification`. Long enough to show what the model actually
#: wrote instead of a labelled rejection; short enough that a state record
#: never grows unboundedly on a model that reliably misses the format.
_UNREADABLE_REPLY_LIMIT = 500


def _truncated(reply: str) -> str:
    """Bound how much of an unreadable reply is kept.

    Args:
        reply: The verification model's raw reply.

    Returns:
        The reply, cut to :data:`_UNREADABLE_REPLY_LIMIT` characters with a
        marker showing it was cut, or left whole if it already fit.
    """
    if len(reply) <= _UNREADABLE_REPLY_LIMIT:
        return reply
    return reply[:_UNREADABLE_REPLY_LIMIT] + "…"
