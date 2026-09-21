"""Tests for bringing the agent up and taking it down again.

These drive the real context manager: a real aiosqlite connection to a real
file, LangGraph's own ``setup()``, the compiled graph, and the teardown. Only
the chat model is injected, which ``open_agent`` already takes as a parameter,
so none of this reaches Ollama or any network.

What is worth proving here is what the lifespan is for. The checkpointer's
tables exist afterwards, a conversation that ran leaves a row behind rather
than living in memory, the usage database is created without anyone having to
make it first, and nothing is left open when the application stops serving.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest
from fastapi import FastAPI

from corpus_query.agent.model import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    load_chat_model,
)
from corpus_query.agent.prompts import PROMPT_DIR, PromptError, load
from corpus_query.agent.runtime import open_agent
from test_agent_answer import ScriptedModel, says


def a_host_app() -> FastAPI:
    """Return an application for the agent to reach retrieval through.

    Nothing is asked of it here — the scripted models below answer without
    searching — but ``open_agent`` builds a client around it, so it has to
    be a real ASGI application.
    """
    return FastAPI()


def test_opening_the_agent_creates_the_checkpointer_tables(tmp_path) -> None:
    """LangGraph's own tables are made on the way up, in the file given."""
    database = tmp_path / "nested" / "usage.db"

    async def run() -> None:
        async with open_agent(
            a_host_app(), model=ScriptedModel([]), checkpoint_database=database
        ):
            pass

    asyncio.run(run())

    assert database.exists()
    connection = sqlite3.connect(database)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert "checkpoints" in tables


def test_a_conversation_survives_the_process_that_held_it(tmp_path) -> None:
    """An answered question leaves a row behind, not a thread in memory.

    This is the whole point of checkpointing to disk: the agent is opened,
    asked something, and closed, and what it did is still there afterwards
    for a later process to resume.
    """
    database = tmp_path / "usage.db"

    async def run() -> str:
        async with open_agent(
            a_host_app(),
            model=ScriptedModel([says("Two weeks out.")]),
            checkpoint_database=database,
        ) as agent:
            answer = await agent.answer("Where are the rev B boards?")
        return answer.thread_id

    thread_id = asyncio.run(run())

    connection = sqlite3.connect(database)
    try:
        (rows,) = connection.execute(
            "SELECT count(*) FROM checkpoints WHERE thread_id = ?", (thread_id,)
        ).fetchone()
    finally:
        connection.close()
    assert rows


def test_closing_the_agent_closes_what_it_opened(tmp_path) -> None:
    """Nothing is left open after the application stops serving.

    aiosqlite runs its connection on a thread of its own, so a connection
    nobody closed is a thread that outlives the server and a file that
    stays locked. Asking the connection to do something after the context
    has exited is how that shows.
    """

    async def run() -> None:
        async with open_agent(
            a_host_app(),
            model=ScriptedModel([]),
            checkpoint_database=tmp_path / "usage.db",
        ) as agent:
            connection = agent.graph.checkpointer.conn
            await connection.execute("SELECT 1")

        with pytest.raises(ValueError, match="no active connection"):
            await connection.execute("SELECT 1")

    asyncio.run(run())


def test_the_graph_is_compiled_with_the_retrieval_tool(tmp_path) -> None:
    """The model that comes up has the search tool bound to it."""
    model = ScriptedModel([])

    async def run() -> None:
        async with open_agent(
            a_host_app(), model=model, checkpoint_database=tmp_path / "usage.db"
        ):
            pass

    asyncio.run(run())

    assert [tool.name for tool in model.bound] == ["search_corpus"]


def test_the_default_usage_database_is_used_when_none_is_given(tmp_path) -> None:
    """Told nothing, it checkpoints to the project's usage database.

    The suite's autouse fixture has already pointed that at ``tmp_path``,
    which is what this asserts against — and the fact that it lands there
    rather than in ``data/`` is the behaviour worth having.
    """

    async def run() -> None:
        async with open_agent(a_host_app(), model=ScriptedModel([])):
            pass

    asyncio.run(run())

    assert (tmp_path / "usage.db").exists()


def test_the_chat_model_is_built_the_way_the_project_wants_it() -> None:
    """The local model is asked for by name, cold, with a sized window.

    Constructing the client does no I/O, so this can assert on the settings
    directly. It pins the context window in particular: 16384 was measured
    against the longest real turns rather than picked, and Ollama's own
    default silently evicts the system prompt when it is too small, so a
    change to that number should be a deliberate one. #87 will rewrite this
    function to choose between backends; these are the settings the local
    one has to keep.
    """
    model = load_chat_model()

    assert model.model == DEFAULT_MODEL == "granite4.1:8b"
    assert model.temperature == DEFAULT_TEMPERATURE == 0.0
    assert model.num_ctx == DEFAULT_CONTEXT_WINDOW == 16384


def test_the_chat_model_takes_overrides() -> None:
    """Every setting can be asked for, which is how a test or a tool pins one."""
    model = load_chat_model(
        model="something-else:1b", temperature=0.7, context_window=2048
    )

    assert (model.model, model.temperature, model.num_ctx) == (
        "something-else:1b",
        0.7,
        2048,
    )


def test_a_prompt_that_is_not_there_is_reported_as_one() -> None:
    """A missing prompt file says which file, not which line of io.py.

    A prompt is loaded by name at startup, so the failure lands a long way
    from the typo that caused it; naming the path is what makes it obvious.
    """
    with pytest.raises(PromptError) as raised:
        load("no-such-prompt")

    assert "no-such-prompt.md" in str(raised.value)
    assert str(PROMPT_DIR) in str(raised.value)


def test_the_answer_prompt_loads() -> None:
    """The prompt the agent actually runs on is where it is looked for."""
    assert "search_corpus" in load("answer")
