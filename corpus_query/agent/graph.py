"""The graph: a model that may search, the loop around it, and what to do
when the search did not settle the question.

Three nodes. ``think`` calls the model. ``tools`` runs whatever the model
asked for and feeds the results back. The edge between them is conditional,
so a question the model answers outright never reaches retrieval at all, and
a question with two halves goes round twice. That loop is the whole reason
the agent exists as a graph rather than a function that searches and then
summarizes.

``route`` runs once, after the model has stopped calling tools, and does
something only for a turn that searched. It asks whether the answer settled
the question, and when it did not, turns the passages that failed to answer
it into a suggestion of who to ask. Its model call is its own: neither the
prompt nor the reply joins the conversation, because a drafted question
appended to the history is something the next turn would try to answer.

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

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from corpus_query.agent.prompts import load
from corpus_query.agent.routing import drafted_question, suggestion

if TYPE_CHECKING:
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

    async def answer(self, question: str, thread_id: str | None = None) -> Answer:
        """Answer one question.

        Args:
            question: The question, in natural language.
            thread_id: The conversation to continue. A new one is started
                when this is not given.

        Returns:
            The answer, its citations, and the conversation it belongs to.
        """
        thread = thread_id or uuid.uuid4().hex
        state = await self.graph.ainvoke(
            {
                "messages": [HumanMessage(question)],
                "system_prompt": self.system_prompt,
                "routing_prompt": self.routing_prompt,
                # Cleared on the way in. State outlives a turn, so a
                # suggestion left over from an earlier question would
                # otherwise come back attached to the answer to this one.
                "routing": None,
                "abstained": False,
            },
            config={"configurable": {"thread_id": thread}},
        )
        turn = _this_turn(state["messages"])
        return Answer(
            answer=_final_text(turn),
            citations=_citations(turn),
            searches=sum(isinstance(message, ToolMessage) for message in turn),
            routing=state.get("routing"),
            abstained=bool(state.get("abstained")),
            thread_id=thread,
        )


class State(MessagesState):
    """The graph's state: the conversation, and the prompt above it.

    The prompt travels as state so that the node reading it does not reach
    back into the object that built the graph, which keeps the node a
    function of its input and lets a test run the graph with a prompt of its
    own.
    """

    system_prompt: str
    routing_prompt: str
    routing: dict[str, Any] | None
    abstained: bool


def build_graph(
    model: BaseChatModel,
    tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver | None = None,
    max_searches: int = MAX_SEARCHES,
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

    Returns:
        The compiled graph.
    """
    with_tools = model.bind_tools(tools)

    async def think(state: State) -> dict[str, list[AIMessage]]:
        """Call the model on the conversation so far.

        Args:
            state: The conversation and the system prompt above it.

        Returns:
            The model's reply, to append to the conversation.
        """
        messages = [SystemMessage(state["system_prompt"]), *state["messages"]]
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

    builder = StateGraph(State)
    builder.add_node("think", think)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("route", route)
    builder.add_edge(START, "think")
    builder.add_conditional_edges(
        "think", tools_condition, {"tools": "tools", END: "route"}
    )
    builder.add_edge("tools", "think")
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
