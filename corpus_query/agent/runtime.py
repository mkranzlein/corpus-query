"""Bringing the agent up, and taking it down again.

Everything the agent needs that outlives a request is opened here and closed
here: the chat model, the client retrieval is reached through, the
checkpointer's connection, and the compiled graph itself. The application's
lifespan enters this context once, so nothing is built per request and
nothing is left open after the process stops serving.

The checkpointer writes to the same SQLite file the corpus lives in. A graph
step that is interrupted — the process stops, the model times out, the laptop
sleeps — leaves a row recording where the run got to, rather than a thread
parked in memory that dies with the process. The tables LangGraph creates are
its own and sit alongside the corpus tables without touching them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from corpus_query.agent.graph import Agent, build_graph
from corpus_query.agent.model import load_chat_model
from corpus_query.agent.retrieval import in_process_client, search_tool
from corpus_query.store.db import DEFAULT_DATABASE_FILE

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
    checkpoint_database: Path | str = DEFAULT_DATABASE_FILE,
) -> AsyncIterator[Agent]:
    """Open everything the agent needs, and compile its graph.

    Args:
        app: The application retrieval is reached through. Requests go to
            it over HTTP semantics rather than by calling into it, so a
            retrieval service elsewhere would be a different client here
            and no change anywhere else.
        model: The chat model to answer with. Defaults to the project's
            local model.
        checkpoint_database: The SQLite file graph state is persisted to.

    Yields:
        The agent, ready to answer.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    chat_model = model if model is not None else load_chat_model()
    client = in_process_client(app)
    connection = await aiosqlite.connect(str(checkpoint_database))
    try:
        checkpointer = AsyncSqliteSaver(connection)
        await checkpointer.setup()
        yield Agent(
            graph=build_graph(
                chat_model, [search_tool(client)], checkpointer=checkpointer
            )
        )
    finally:
        await connection.close()
        await client.aclose()
