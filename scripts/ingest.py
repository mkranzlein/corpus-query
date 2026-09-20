"""Ingest documents into the document store.

Reads whatever the pipeline has a reader for, splits each document along its
own seams, and writes documents, attendees, and chunks. Nothing here calls a
model, and nothing costs anything: the run is deterministic, so ingesting the
same corpus twice leaves the store in the same state.

Run it with::

    uv run scripts/ingest.py                     # everything on disk
    uv run scripts/ingest.py data/transcripts/rev-b-schedule.md

Re-ingesting a document replaces the rows it wrote before rather than adding a
second copy, so this is also how an edited document is brought up to date.
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
    document_paths,
    ingest_paths,
)
from corpus_query.store.db import DEFAULT_DATABASE_FILE, SchemaVersionError, connect


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Arguments to parse. Defaults to the process arguments.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Ingest documents into the document store.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="documents to ingest (default: every readable file in --dir)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_TRANSCRIPT_DIR,
        dest="directory",
        help=f"where documents live (default: {DEFAULT_TRANSCRIPT_DIR})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE_FILE,
        help=f"document store to write to (default: {DEFAULT_DATABASE_FILE})",
    )
    return parser.parse_args(argv)


def describe(result: Ingested) -> str:
    """Say what ingesting one document did.

    Args:
        result: What the ingest returned.

    Returns:
        One line, naming the document and what it produced, counted in
        whatever unit its format reads in.
    """
    what = "replaced" if result.replaced else "added"
    return (
        f"  {what} {result.slug}: {result.units} {result.unit_name}, "
        f"{result.chunks} chunks"
    )


def main(argv: list[str] | None = None) -> int:
    """Run the script.

    Args:
        argv: Command-line arguments. Defaults to the process arguments.

    Returns:
        A process exit code. Non-zero if any file could not be ingested.
    """
    args = parse_args(argv)
    paths = args.paths or document_paths(args.directory)
    if not paths:
        print(
            f"error: no readable documents found in {args.directory}. Generate "
            f"some first, or name the files to ingest.",
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
        f"Ingested {len(done)} of {len(paths)} documents, {chunks} chunks, "
        f"into {args.db}."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
