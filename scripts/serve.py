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

Nothing here calls a hosted model and nothing costs anything: search runs
locally against the store and the local models.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from corpus_query.api.app import StartupError, create_app, open_resources
from corpus_query.retrieval.index import DEFAULT_INDEX_DIR
from corpus_query.store.db import DEFAULT_DATABASE_FILE, SchemaVersionError

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
        resources = open_resources(args.db, args.index)
    except (StartupError, SchemaVersionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # The resources are opened here rather than inside the application's
    # lifespan so that a bad corpus is reported as one clear line before
    # uvicorn starts, instead of a traceback out of a startup hook.
    app = create_app(resources=lambda: resources)
    print(f"Serving {args.db} on http://{args.host}:{args.port}")
    run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
