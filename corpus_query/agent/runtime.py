"""Bringing the agent up, and taking it down again.

Everything the agent needs that outlives a request is opened here and closed
here: the chat model, the client retrieval is reached through, the
checkpointer's connection, and the compiled graph itself. The application's
lifespan enters this context once, so nothing is built per request and
nothing is left open after the process stops serving.

The checkpointer writes to the usage database. A graph step that is
interrupted — the process stops, the model times out, the laptop sleeps —
leaves a row recording where the run got to, rather than a thread parked in
memory that dies with the process.

That is a separate SQLite file from the corpus, and deliberately so. The
corpus is committed and read-only in normal use; conversations are local,
grow with use, and belong to whoever is running the service. See
:mod:`corpus_query.store.usage`. The file does not have to exist beforehand —
``setup()`` creates LangGraph's tables in it on the way up.

The same file holds the captured records — gaps, corrections, feedback — and
the agent opens its own connection to them, because a correction the user
types in conversation is recorded by the agent rather than by the endpoint.
It writes through :mod:`corpus_query.store.capture`, the same store ``POST
/corrections`` writes to, so a correction reads back the same way whichever
of the two recorded it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from corpus_query.agent.graph import Agent, build_graph
from corpus_query.agent.model import load_chat_model
from corpus_query.agent.retrieval import in_process_client, search_tool
from corpus_query.store import capture
from corpus_query.store.usage import usage_database

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

#: Opens the agent for the lifetime of an application, given that
#: application — which the agent needs because it reaches retrieval by
#: posting to it.
type OpenAgent = Callable[[Any], "AsyncIterator[Agent]"]


@asynccontextmanager
async def open_agent(
    app: Any,
    model: BaseChatModel | None = None,
    checkpoint_database: Path | str | None = None,
) -> AsyncIterator[Agent]:
    """Open everything the agent needs, and compile its graph.

    Args:
        app: The application retrieval is reached through. Requests go to
            it over HTTP semantics rather than by calling into it, so a
            retrieval service elsewhere would be a different client here
            and no change anywhere else.
        model: The chat model to answer with. Defaults to the project's
            local model.
        checkpoint_database: The usage database graph state is persisted
            to, and corrections typed in conversation are recorded in.
            Created, with its directory, if it is not there yet. None
            resolves to the project's default when the agent opens, not
            when this module is imported.

    Yields:
        The agent, ready to answer.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    chat_model = model if model is not None else load_chat_model()
    client = in_process_client(app)
    connection = await aiosqlite.connect(str(usage_database(checkpoint_database)))
    try:
        checkpointer = AsyncSqliteSaver(connection)
        await checkpointer.setup()
        # Opened on the event loop's thread, which is the thread every node
        # of the graph runs on, so the connection is never used from a
        # thread other than the one that opened it.
        captured = capture.connect(checkpoint_database)
        try:
            yield Agent(
                graph=build_graph(
                    chat_model,
                    [search_tool(client)],
                    checkpointer=checkpointer,
                    record_correction=partial(capture.record_correction, captured),
                )
            )
        finally:
            captured.close()
    finally:
        await connection.close()
        await client.aclose()
