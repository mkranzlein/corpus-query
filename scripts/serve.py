"""Serve the query API.

Opens the document store, opens the vector index — rebuilding it from the
embeddings already in the store if it is missing or stale — loads the
embedding and reranking models, and then starts serving. All of that happens
before the socket is listening, so the first query costs no more than the
tenth and a corpus that is not there is a refusal to start rather than a
service that answers everything with no results.

Run it with::

    uv sync --extra models                     # once: the embedder, reranker
    uv run scripts/serve.py             # http://127.0.0.1:8000
    uv run scripts/serve.py --port 9000

Two SQLite files are involved and they are not the same one. ``--db`` is the
corpus, which is read to answer questions and never written to here.
``--usage-db`` is where conversations are checkpointed and where gaps,
corrections, and feedback are recorded; it is created on first use, it is not
committed, and it is the only file serving modifies.

Search runs locally against the store and the local models, and costs
nothing. So does ``/answer`` by default: it answers from a model served
locally by Ollama, which needs to be running and to have that model pulled.
Setting ``CORPUS_QUERY_MODEL_BACKEND=bedrock`` answers from the hosted model
instead, which makes a real, billed call per question. Whichever is chosen is
built before the socket is open and printed on the way up, so a missing key
or a misspelled backend is one line and a non-zero exit rather than a failure
on the first question.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import uvicorn

from corpus_query.agent.model import (
    ModelConfigurationError,
    load_chat_model,
    selected_backend,
)
from corpus_query.agent.runtime import open_agent
from corpus_query.api.app import StartupError, create_app, open_resources
from corpus_query.retrieval.index import DEFAULT_INDEX_DIR
from corpus_query.store.capture import CaptureSchemaVersionError
from corpus_query.store.db import DEFAULT_DATABASE_FILE, SchemaVersionError
from corpus_query.store.usage import DEFAULT_USAGE_DATABASE_FILE

#: Loopback by default. This is a local service over a local corpus, and
#: there is no authentication in front of it.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Arguments to parse. Defaults to the process arguments.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Serve the query API.")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE_FILE,
        help=f"document store to serve (default: {DEFAULT_DATABASE_FILE})",
    )
    parser.add_argument(
        "--usage-db",
        type=Path,
        default=DEFAULT_USAGE_DATABASE_FILE,
        help=f"where conversations, gaps, corrections, and feedback are "
        f"recorded, created if it is not there "
        f"(default: {DEFAULT_USAGE_DATABASE_FILE})",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help=f"where the vector index lives (default: {DEFAULT_INDEX_DIR})",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"address to bind (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"port to bind (default: {DEFAULT_PORT})",
    )
    return parser.parse_args(argv)


def chat_model_name(model: Any) -> str:
    """Name the model that was built, for the line printed on the way up.

    Args:
        model: The chat model the agent will answer with.

    Returns:
        What the backend calls it, so the printed line says which model is
        about to answer rather than only which backend it came from.
    """
    return str(getattr(model, "model", "") or getattr(model, "model_id", "?"))


def main(argv: list[str] | None = None, run=uvicorn.run) -> int:
    """Run the script.

    Args:
        argv: Command-line arguments. Defaults to the process arguments.
        run: What to serve the application with. Overridable in tests so
            nothing binds a socket.

    Returns:
        A process exit code. Non-zero if the service could not be brought up.
    """
    args = parse_args(argv)
    try:
        resources = open_resources(args.db, args.index, usage_database=args.usage_db)
        backend = selected_backend()
        chat_model = load_chat_model(backend)
    except (
        StartupError,
        SchemaVersionError,
        CaptureSchemaVersionError,
        ModelConfigurationError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # The resources are opened here rather than inside the application's
    # lifespan so that a bad corpus is reported as one clear line before
    # uvicorn starts, instead of a traceback out of a startup hook.
    app = create_app(
        resources=lambda: resources,
        agent=lambda application: open_agent(
            application, model=chat_model, checkpoint_database=args.usage_db
        ),
    )
    print(f"Serving {args.db} on http://{args.host}:{args.port}")
    print(f"/answer is answering from {chat_model_name(chat_model)} on {backend}.")
    print("The page is at that address; /search, /answer, and /health are below it.")
    run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
