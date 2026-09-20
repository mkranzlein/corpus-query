"""Ingest transcripts into the document store.

Reads rendered transcripts, splits them into chunks of whole turns, and writes
documents, attendees, and chunks. Nothing here calls a model, and nothing costs
anything: the run is deterministic, so ingesting the same corpus twice leaves
the store in the same state.

Run it with::

    uv run python -m scripts.ingest                     # everything on disk
    uv run python -m scripts.ingest data/transcripts/rev-b-schedule.md

Re-ingesting a transcript replaces the rows it wrote before rather than adding
a second copy, so this is also how an edited transcript is brought up to date.
Each document is written in one transaction: a file that fails is reported and
skipped, and leaves nothing behind.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus_query.ingest.pipeline import (
    DEFAULT_TRANSCRIPT_DIR,
    Ingested,
    ingest_paths,
    transcript_paths,
)
from corpus_query.store.db import SchemaVersionError, connect
from corpus_query.transcripts.summaries import DEFAULT_DATABASE_FILE


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Arguments to parse. Defaults to the process arguments.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Ingest transcripts into the document store.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="transcripts to ingest (default: every markdown file in --dir)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_TRANSCRIPT_DIR,
        dest="directory",
        help=f"where transcripts live (default: {DEFAULT_TRANSCRIPT_DIR})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE_FILE,
        help=f"document store to write to (default: {DEFAULT_DATABASE_FILE})",
    )
    return parser.parse_args(argv)


def describe(result: Ingested) -> str:
    """Say what ingesting one transcript did.

    Args:
        result: What the ingest returned.

    Returns:
        One line, naming the document and what it produced.
    """
    what = "replaced" if result.replaced else "added"
    return f"  {what} {result.slug}: {result.turns} turns, {result.chunks} chunks"


def main(argv: list[str] | None = None) -> int:
    """Run the script.

    Args:
        argv: Command-line arguments. Defaults to the process arguments.

    Returns:
        A process exit code. Non-zero if any file could not be ingested.
    """
    args = parse_args(argv)
    paths = args.paths or transcript_paths(args.directory)
    if not paths:
        print(
            f"error: no transcripts found in {args.directory}. Generate some "
            f"first, or name the files to ingest.",
            file=sys.stderr,
        )
        return 1

    args.db.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = connect(args.db)
    except SchemaVersionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        done, failures = ingest_paths(connection, paths)
    finally:
        connection.close()

    for result in done:
        print(describe(result))
    for failure in failures:
        print(f"error: {failure}", file=sys.stderr)

    chunks = sum(result.chunks for result in done)
    print(
        f"Ingested {len(done)} of {len(paths)} transcripts, {chunks} chunks, "
        f"into {args.db}."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
