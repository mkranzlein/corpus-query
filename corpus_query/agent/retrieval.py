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
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from corpus_query.retrieval.search import DEFAULT_RESULTS

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

#: What the tool is called in the model's tool schema. Named for what it
#: searches, so a model deciding whether to call it is deciding whether the
#: question is about this corpus.
TOOL_NAME = "search_corpus"

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

    async def search_corpus(query: str) -> tuple[str, list[dict[str, Any]]]:
        """Run one search and return passages for the model and citations.

        Args:
            query: What to search for.

        Returns:
            The passages as the model reads them, and the same passages as
            structured citations.

        Raises:
            httpx.HTTPStatusError: If the search endpoint refused the
                request. Left to surface: a retrieval failure the model
                narrated around would be worse than one that is reported.
        """
        response = await client.post(path, json={"query": query, "limit": limit})
        response.raise_for_status()
        payload = response.json()
        results = payload["results"]
        confidence = payload.get("confidence") or {}
        return (
            render_passages(results, confidence.get("unmatched_terms") or []),
            [citation(result) for result in results],
        )

    return StructuredTool.from_function(
        coroutine=search_corpus,
        name=TOOL_NAME,
        description=(
            "Search this organization's own record — its meetings, "
            "documents, decks, and spreadsheets — and return the passages "
            "that bear on a question, each with the document and place it "
            "came from. Call it once per subject you need to look up."
        ),
        args_schema=SearchCorpus,
        response_format="content_and_artifact",
    )


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
        "location": result["location"],
    }


def render_passages(
    results: list[dict[str, Any]], unmatched_terms: list[str] | None = None
) -> str:
    """Render search results as the text the model reads.

    Each passage is labelled with where it came from, so a model told to
    attribute every claim to a passage has something to attribute it to.

    Args:
        results: The results from one search, best first.
        unmatched_terms: Query terms that matched nothing lexically.
            Reported because a name the corpus does not have is usually the
            reason a search came back thin.

    Returns:
        The passages as one block of text. When nothing matched, a line
        saying so — which is a result the model is meant to act on, not an
        empty string it might read as a glitch.
    """
    if not results:
        empty = "No passages in the record matched that search."
        if unmatched_terms:
            empty += (
                " These terms appear nowhere in the record: "
                f"{', '.join(unmatched_terms)}."
            )
        return empty

    blocks = []
    for index, result in enumerate(results, start=1):
        source = f"{result['title']} ({result['document_date']}"
        if result["author"]:
            source += f", {result['author']}"
        source += f", {result['location']})"
        blocks.append(f"[{index}] {source}\n{result['text']}")
    rendered = "\n\n".join(blocks)
    if unmatched_terms:
        rendered += (
            f"\n\nNot found anywhere in the record: {', '.join(unmatched_terms)}."
        )
    return rendered
