"""Enrich ingested documents with summaries, topics, priority, and embeddings.

Reads documents out of the store, asks a model for what only a model can
produce, and writes it back: a summary, up to five topics from a shared
category list, a time sensitivity, a business impact, and an embedding for
every chunk. A dedupe pass at the end folds near-duplicate categories
together.

Run it with::

    uv sync --extra models                            # once: the embedder
    uv run python -m scripts.enrich --dry-run         # print the prompts
    uv run python -m scripts.enrich                   # everything unenriched
    uv run python -m scripts.enrich rev-b-schedule    # named documents

The embedding model comes from the ``models`` extra, which a plain
``uv sync`` does not install. Without it every other pass would still run and
the embedding pass would fail at the last step, so the run stops up front
instead, with the command to fix it.

Settings come from ``.env``: ``OPENAI_API_KEY``, ``OPENAI_BASE_URL``, and
``OPENAI_PROJECT``.

Every run without ``--dry-run`` makes real, billed inference calls — several
per document. Do not run this without asking first; see CLAUDE.md.

Documents are enriched one at a time, on purpose: each one is filed against
the categories the ones before it created, which is what keeps the category
list from fragmenting. Each document is written in one transaction, so a
failure part way through a corpus leaves the documents already finished
enriched and the rest untouched.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from openai import OpenAI

from corpus_query.enrich import passes
from corpus_query.enrich.documents import ids_for_slugs, pending_ids, read_document
from corpus_query.enrich.embed import Embed
from corpus_query.enrich.errors import EnrichmentError
from corpus_query.enrich.pipeline import (
    Enriched,
    dedupe_categories,
    enrich_documents,
    seed_store,
)
from corpus_query.enrich.prompts import PromptError
from corpus_query.enrich.topics import DEFAULT_TOPICS_FILE, list_categories
from corpus_query.store.db import DEFAULT_DATABASE_FILE, SchemaVersionError, connect
from infra.config import ConfigError, load_env, require

#: Environment file this script reads, holding the OpenAI-compatible client
#: settings rather than the AWS provisioning ones.
ENV_FILE = ".env"

#: A plain Bedrock model id, not a ``us.``-prefixed inference profile.
MODEL = "openai.gpt-5.6-sol"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Arguments to parse. Defaults to the process arguments.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Enrich ingested documents with summaries, topics, priority, "
            "and embeddings."
        ),
    )
    parser.add_argument(
        "slugs",
        nargs="*",
        help=(
            "documents to enrich, named by slug (default: every document "
            "that has not been enriched yet)"
        ),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE_FILE,
        help=f"document store to enrich (default: {DEFAULT_DATABASE_FILE})",
    )
    parser.add_argument(
        "--topics",
        type=Path,
        default=DEFAULT_TOPICS_FILE,
        help=f"the seeded category list (default: {DEFAULT_TOPICS_FILE})",
    )
    parser.add_argument("--model", default=MODEL, help=f"model id (default: {MODEL})")
    parser.add_argument(
        "--recompute-embeddings",
        action="store_true",
        help="re-embed chunks that already have an embedding",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="skip the pass that merges near-duplicate categories",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the prompts that would be sent and exit without calling anything",
    )
    return parser.parse_args(argv)


def build_client(env: dict[str, str]) -> OpenAI:
    """Build the OpenAI client pointed at the Bedrock endpoint.

    Args:
        env: Settings as returned by :func:`infra.config.load_env`.

    Returns:
        A client configured with the key, endpoint, and project from ``env``.

    Raises:
        ConfigError: If a required setting is missing.
    """
    return OpenAI(
        api_key=require(env, "OPENAI_API_KEY"),
        base_url=require(env, "OPENAI_BASE_URL"),
        project=require(env, "OPENAI_PROJECT"),
    )


def build_embedder() -> tuple[Embed, str]:
    """Load the project's embedder.

    Returns:
        The passage-side embedding function, and the model id recorded with
        every vector it produces.

    Raises:
        EnrichmentError: If the models extra is not installed. Checked
            before any billed call rather than at the end of the first
            document, where the fix would be the same and the bill would
            not.
    """
    try:
        from corpus_query.models.embedder import EMBEDDING_MODEL_ID, embed_documents
    except ImportError as exc:
        raise EnrichmentError(
            f"The embedding model is not installed ({exc}). Run "
            f"`uv sync --extra models` and try again."
        ) from exc
    return embed_documents, EMBEDDING_MODEL_ID


def describe(result: Enriched) -> str:
    """Say what enriching one document did.

    Args:
        result: What the enrichment returned.

    Returns:
        Two lines: the document and its fields, then its summary.
    """
    embedded = result.embedded
    topics = ", ".join(result.topics) or "no topics"
    return (
        f"  {result.slug}: {topics} | {result.time_sensitivity} / "
        f"{result.business_impact} | {embedded.written} embedded, "
        f"{embedded.skipped} already had one\n"
        f"    {result.summary}"
    )


def print_prompts(connection, document_ids: list[int], categories: list[str]) -> None:
    """Print what would be sent, for every selected document.

    The category list shown is the one that exists now. In a real run it
    grows as documents are enriched, so a dry run over several documents
    understates what the later ones would see.

    Args:
        connection: An open document store.
        document_ids: The documents that would be enriched.
        categories: The categories that exist right now.
    """
    for document_id in document_ids:
        document = read_document(connection, document_id)
        for name, prompt in (
            ("summary", passes.summary_prompt(document)),
            ("topics", passes.topics_prompt(document, categories)),
            ("priority", passes.priority_prompt(document)),
        ):
            print(f"===== {document.slug}: {name} =====")
            print(prompt)
    print("===== dedupe =====")
    print(passes.dedupe_prompt(categories))


def main(
    argv: list[str] | None = None,
    client_factory: Callable[[dict[str, str]], OpenAI] = build_client,
    embedder_factory: Callable[[], tuple[Embed, str]] = build_embedder,
) -> int:
    """Run the script.

    Args:
        argv: Command-line arguments. Defaults to the process arguments.
        client_factory: Builds the client from settings. Overridable in
            tests so a fake client can stand in for the real one.
        embedder_factory: Loads the embedder. Overridable in tests so no
            model is loaded and no weights are downloaded.

    Returns:
        A process exit code. Non-zero if any document could not be enriched.
    """
    args = parse_args(argv)
    if not args.db.is_file():
        print(
            f"error: there is no document store at {args.db}. Ingest some "
            f"transcripts first.",
            file=sys.stderr,
        )
        return 1

    try:
        connection = connect(args.db)
    except SchemaVersionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        return _run(args, connection, client_factory, embedder_factory)
    except (EnrichmentError, PromptError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()


def _run(
    args: argparse.Namespace,
    connection,
    client_factory: Callable[[dict[str, str]], OpenAI],
    embedder_factory: Callable[[], tuple[Embed, str]],
) -> int:
    """Do the work, with the store open.

    Args:
        args: The parsed command line.
        connection: An open document store.
        client_factory: Builds the client from settings.
        embedder_factory: Loads the embedder.

    Returns:
        A process exit code.

    Raises:
        EnrichmentError: If the seed list or a named document cannot be
            read, or the embedder is not installed.
        PromptError: If a prompt template is missing or does not match what
            fills it.
        ConfigError: If a client setting is missing.
    """
    added = seed_store(connection, args.topics)
    if added:
        print(f"Seeded {len(added)} categories.")

    document_ids = (
        ids_for_slugs(connection, args.slugs) if args.slugs else pending_ids(connection)
    )
    if not document_ids:
        print("Nothing to enrich: every document in the store has a summary.")
        return 0

    if args.dry_run:
        print_prompts(connection, document_ids, list_categories(connection))
        return 0

    embed, embedding_model_id = embedder_factory()
    client = client_factory(load_env(ENV_FILE))

    print(f"Enriching {len(document_ids)} documents with {args.model}, in order.")
    done, failures = enrich_documents(
        connection,
        client,
        args.model,
        document_ids,
        recompute_embeddings=args.recompute_embeddings,
        embed=embed,
        embedding_model_id=embedding_model_id,
    )
    for result in done:
        print(describe(result))
    for failure in failures:
        print(f"error: {failure.slug}: {failure.error}", file=sys.stderr)

    if not args.no_dedupe:
        _dedupe(connection, client, args.model)

    print(f"Enriched {len(done)} of {len(document_ids)} documents in {args.db}.")
    return 1 if failures else 0


def _dedupe(connection, client: OpenAI, model: str) -> None:
    """Run the dedupe pass and report what it merged.

    A failure here is printed rather than raised. Every document is already
    written by this point, and a category list that still holds a duplicate
    pair is worth strictly less than the enrichment that produced it.

    Args:
        connection: An open document store.
        client: A configured client.
        model: The model id to call.
    """
    try:
        merges = dedupe_categories(connection, client, model)
    except (EnrichmentError, PromptError) as exc:
        print(f"error: the dedupe pass failed: {exc}", file=sys.stderr)
        return
    for merge in merges:
        folded = ", ".join(merge.merged)
        print(
            f"  merged {folded} into {merge.keep}: {merge.repointed} moved, "
            f"{merge.collapsed} already filed under both"
        )
    if not merges:
        print("The category list had no duplicates to merge.")


if __name__ == "__main__":
    raise SystemExit(main())
