"""Retrieval, as a tool the agent calls over HTTP.

The agent does not import :func:`corpus_query.retrieval.search.search`. It
posts to ``/search`` the way any other client would, over real HTTP semantics
— a request body, a status code, a JSON response — and only the transport
underneath differs. In process that transport is
:class:`httpx.ASGITransport`, which hands the request straight to the
application object with no socket and no server; pointed at a retrieval
service running somewhere else, it is an ordinary client with a base URL and
nothing above it changes.

That is the point of doing it this way. Splitting retrieval out into its own
process later is a base URL, not a rewrite of the agent, and the shapes the
agent is written against are the published ones in
:mod:`corpus_query.api.models` rather than an internal dataclass that is free
to change underneath it.

What the tool hands back is split in two. The model sees rendered passages —
text with the document, date, and place it came from, which is what it needs
to answer and to say where the answer came from. Alongside that, as the tool
message's artifact, go the same passages as structured citations, which is
what the response carries back to the caller. Both come from one search, so
what the answer cites and what the model read cannot drift apart.

The artifact also keeps what the answer's row is measured with: each passage
as the model was shown it, which citation coverage is checked against, and
the search's top score and margin. See :func:`found` for its shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

import httpx
from langchain_core.tools import InjectedToolCallId, StructuredTool
from pydantic import BaseModel, Field

from corpus_query import tracing
from corpus_query.retrieval.search import DEFAULT_RESULTS

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

#: What the tool is called in the model's tool schema. Named for what it
#: searches, so a model deciding whether to call it is deciding whether the
#: question is about this corpus.
TOOL_NAME = "search_corpus"

#: What the model is told the tool does, and what its span describes it as.
TOOL_DESCRIPTION = (
    "Search this organization's own record — its meetings, documents, decks, "
    "and spreadsheets — and return the passages that bear on a question, each "
    "with the document and place it came from. Call it once per subject you "
    "need to look up."
)

#: The path the tool posts to, on whatever host it is pointed at.
SEARCH_PATH = "/search"

#: The base URL used when the tool talks to the application in process. No
#: name is resolved and no socket is opened, so the host is a label; it
#: exists because httpx requires an absolute URL to build a request from.
IN_PROCESS_BASE_URL = "http://retrieval.internal"


class SearchCorpus(BaseModel):
    """The tool's arguments, as the model is shown them."""

    query: str = Field(
        description="What to search for, written as a plain-language "
        "question or phrase. One subject per search."
    )
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None
    """Which of the model's calls this is. Filled in by LangChain from the
    call itself and never shown to the model; recorded on the tool's span."""


def in_process_client(
    app: Any, base_url: str = IN_PROCESS_BASE_URL
) -> httpx.AsyncClient:
    """Build a client that reaches an ASGI application without a socket.

    Args:
        app: The ASGI application to send requests to.
        base_url: What to resolve relative paths against. A label rather
            than an address, since nothing is dialed.

    Returns:
        An open client. The caller closes it.
    """
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base_url)


def search_tool(
    client: httpx.AsyncClient,
    limit: int = DEFAULT_RESULTS,
    path: str = SEARCH_PATH,
) -> BaseTool:
    """Build the retrieval tool the agent is given.

    Args:
        client: What to post searches with. Its base URL decides whether
            retrieval is this application or another service.
        limit: How many passages one search returns.
        path: The search endpoint's path on that base URL.

    Returns:
        The tool, ready to be bound to a model.
    """

    async def search_corpus(
        query: str, tool_call_id: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Run one search and return passages for the model and citations.

        The search runs inside a tool span, and the request carries that
        span's trace context in its headers, so the retrieval spans the
        endpoint opens belong to this call's trace whether ``/search`` is
        this process or another one.

        Args:
            query: What to search for.
            tool_call_id: The model's id for this call, when it came from
                one.

        Returns:
            The passages as the model reads them, and what :func:`found`
            reads back out of the tool message: the same passages as
            structured citations, their text, and the search's confidence.

        Raises:
            httpx.HTTPStatusError: If the search endpoint refused the
                request. Left to surface: a retrieval failure the model
                narrated around would be worse than one that is reported.
        """
        with tracing.span(
            f"execute_tool {TOOL_NAME}",
            {
                tracing.OPERATION: "execute_tool",
                tracing.TOOL_NAME: TOOL_NAME,
                tracing.TOOL_TYPE: "function",
                tracing.TOOL_DESCRIPTION: TOOL_DESCRIPTION,
                tracing.TOOL_CALL_ID: tool_call_id,
                tracing.RETRIEVAL_QUERY: query,
            },
        ) as calling:
            response = await client.post(
                path,
                json={"query": query, "limit": limit},
                headers=tracing.headers(),
            )
            response.raise_for_status()
            payload = response.json()
            results = payload["results"]
            confidence = payload.get("confidence") or {}
            tracing.annotate(
                calling,
                {
                    "corpus_query.retrieval.result_count": len(results),
                    **tracing.confidence_attributes(confidence),
                },
            )
        return (
            render_passages(query, results, confidence.get("unmatched_terms") or []),
            {
                "citations": [citation(result) for result in results],
                "passages": [passage(result) for result in results],
                "confidence": {
                    "top_score": confidence.get("top_score"),
                    "margin": confidence.get("margin"),
                },
            },
        )

    return StructuredTool.from_function(
        coroutine=search_corpus,
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        args_schema=SearchCorpus,
        response_format="content_and_artifact",
    )


def found(artifact: Any) -> dict[str, Any]:
    """Read what one search found back out of its tool message's artifact.

    The artifact is plain data, because it is checkpointed with the rest of
    the conversation. A thread checkpointed before the artifact carried
    passages and confidence holds a bare list of citations, and is read as
    that list with nothing else known about the search.

    Args:
        artifact: A search tool message's artifact, or None.

    Returns:
        ``citations``, the passages as the answer cites them; ``passages``,
        the same passages as the model was shown them; and ``confidence``,
        the search's ``top_score`` and ``margin``. Each is empty when the
        artifact does not say.
    """
    if isinstance(artifact, dict):
        return {
            "citations": list(artifact.get("citations") or []),
            "passages": list(artifact.get("passages") or []),
            "confidence": dict(artifact.get("confidence") or {}),
        }
    return {"citations": list(artifact or []), "passages": [], "confidence": {}}


def citation(result: dict[str, Any]) -> dict[str, Any]:
    """Reduce one search result to what a citation shows.

    Args:
        result: One result, as ``/search`` returns it.

    Returns:
        The fields that identify the passage, without its text or its
        ranking scores. Plain data, because it is checkpointed alongside
        the rest of the graph's state.
    """
    return {
        "chunk_id": result["chunk_id"],
        "document_slug": result["document_slug"],
        "source_kind": result["source_kind"],
        "title": result["title"],
        "document_date": result["document_date"],
        "author": result["author"],
        "attendees": list(result.get("attendees") or []),
        "location": result["location"],
    }


def render_passages(
    query: str,
    results: list[dict[str, Any]],
    unmatched_terms: list[str] | None = None,
) -> str:
    """Render search results as the text the model reads.

    Each passage is labelled with where it came from, so a model told to
    attribute every claim to a passage has something to attribute it to.

    The block opens with a line saying what was searched for and that
    ranking is not relevance. That instruction is also in the system
    prompt, and it is repeated here on purpose: retrieval cannot return
    nothing, so a question the corpus never covered still comes back with
    five confident-looking passages, and a small model reading a page of
    business writing will summarize it unless something close at hand says
    not to. The tool result is the last thing it reads before answering,
    which is where the reminder does the most work.

    Args:
        query: What was searched for, echoed so a model that ran two
            searches can tell the results apart.
        results: The results from one search, best first.
        unmatched_terms: Query terms that matched nothing lexically.
            Reported because a name the corpus does not have is usually the
            reason a search came back thin.

    Returns:
        The passages as one block of text. When nothing matched, a line
        saying so — which is a result the model is meant to act on, not an
        empty string it might read as a glitch.
    """
    missing = (
        f" Nothing in the record contains: {', '.join(unmatched_terms)}."
        if unmatched_terms
        else ""
    )
    if not results:
        return f'No passages matched "{query}".{missing}'

    blocks = [
        f"[{index}] {passage(result)}" for index, result in enumerate(results, start=1)
    ]
    return (
        f'The {len(results)} closest passages to "{query}".{missing} Closest is '
        f"not the same as relevant: read them against the question you were "
        f"asked, and if none of them answers it, say the record does not say "
        f"rather than summarizing what is here.\n\n" + "\n\n".join(blocks)
    )


def passage(result: dict[str, Any]) -> str:
    """Render one search result as the model reads it, without its number.

    Args:
        result: One result, as ``/search`` returns it.

    Returns:
        A line saying where the passage came from — title, date, author or
        attendees, and location — and then the passage's text.
    """
    source = f"{result['title']} ({result['document_date']}"
    if result["author"]:
        source += f", {result['author']}"
    elif result.get("attendees"):
        source += f", {', '.join(result['attendees'])}"
    source += f", {result['location']})"
    return f"{source}\n{result['text']}"
