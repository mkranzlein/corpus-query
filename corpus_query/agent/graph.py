"""The graph: a model that may search, and the loop around it.

Two nodes. ``think`` calls the model. ``tools`` runs whatever the model asked
for and feeds the results back. The edge between them is conditional, so a
question the model answers outright never reaches retrieval at all, and a
question with two halves goes round twice. That loop is the whole reason the
agent exists as a graph rather than a function that searches and then
summarizes.

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

    thread_id: str
    """The conversation this turn belongs to. Passing it back continues the
    conversation; leaving it out starts a new one."""


@dataclass(frozen=True)
class Agent:
    """A compiled graph and the conversation it is invoked through."""

    graph: Any
    """The compiled LangGraph graph. Compiled once, awaited per request."""

    system_prompt: str = field(default_factory=lambda: load("answer"))

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
            },
            config={"configurable": {"thread_id": thread}},
        )
        turn = _this_turn(state["messages"])
        return Answer(
            answer=_final_text(turn),
            citations=_citations(turn),
            searches=sum(isinstance(message, ToolMessage) for message in turn),
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

    builder = StateGraph(State)
    builder.add_node("think", think)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "think")
    builder.add_conditional_edges(
        "think", tools_condition, {"tools": "tools", END: END}
    )
    builder.add_edge("tools", "think")
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


def _final_text(messages: list[Any]) -> str:
    """Return the text of the last thing the model said.

    Args:
        messages: This turn's messages.

    Returns:
        The answer, or an empty string if the model said nothing at all.
    """
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message.text if isinstance(message.text, str) else str(message.text)
    return ""


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
