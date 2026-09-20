"""Enriching a corpus, one document at a time.

Two properties shape this module.

Documents are processed **sequentially**, which is a correctness requirement
rather than a performance preference. Each topic pass is shown the categories
every earlier document produced, so the list converges on a shared
vocabulary. Run in parallel, every document would be filed against the same
stale list, and the result would be exactly the fragmentation the dedupe pass
exists to clean up — except worse, because there would be more of it.

One document's enrichment is **one transaction**. The summary, the summary
chunk, the topics, the priority fields, and the embeddings land together or
not at all, so "enriched" is never half true. The model calls happen before
the transaction opens, so a slow or failing call never holds one. A document
that fails is reported and the run moves on: the ones already written stay
written, and re-running picks up where it stopped.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from corpus_query.enrich import passes
from corpus_query.enrich.dedupe import Merged, apply_merges
from corpus_query.enrich.documents import StoredDocument, read_document
from corpus_query.enrich.embed import Embed, Embedded, embed_document
from corpus_query.enrich.errors import EnrichmentError
from corpus_query.enrich.prompts import PromptError
from corpus_query.enrich.schema import PriorityAssessment
from corpus_query.enrich.topics import (
    DEFAULT_TOPICS_FILE,
    assign_topics,
    list_categories,
    read_seed_topics,
    seed_categories,
)
from corpus_query.ingest.chunk import count_words
from corpus_query.store.kinds import SUMMARY


#: What a citation shows for the summary chunk. It stands for the whole
#: document rather than any part of it, and says so.
SUMMARY_LOCATION = "summary"


@dataclass(frozen=True)
class Enriched:
    """What enriching one document produced."""

    document_id: int
    slug: str
    summary: str
    topics: tuple[str, ...]
    time_sensitivity: str
    business_impact: str
    embedded: Embedded


@dataclass(frozen=True)
class Failure:
    """A document that could not be enriched, and why."""

    document_id: int
    slug: str
    error: Exception


def seed_store(
    connection: sqlite3.Connection, path: Path | str = DEFAULT_TOPICS_FILE
) -> list[str]:
    """Put the seeded starting categories into the store.

    Called before a run rather than at ingest time, so that a corpus
    ingested before this pass existed still gets the seed list. Adding a
    category that is already there is not an error; it does nothing.

    Args:
        connection: An open document store.
        path: The committed seed list.

    Returns:
        The categories this call added.

    Raises:
        EnrichmentError: If the seed list cannot be read.
    """
    names = read_seed_topics(path)
    with connection:
        return seed_categories(connection, names)


def enrich_document(
    connection: sqlite3.Connection,
    client: object,
    model: str,
    document_id: int,
    recompute_embeddings: bool = False,
    embed: Embed | None = None,
    embedding_model_id: str | None = None,
) -> Enriched:
    """Enrich one document and write the result in one transaction.

    Args:
        connection: An open document store.
        client: A configured client.
        model: The model id to call.
        document_id: The document to enrich.
        recompute_embeddings: Re-embed chunks that already have a vector.
        embed: What to embed with. Defaults to the project's embedder.
        embedding_model_id: What to record as having produced the vectors.
            Required when ``embed`` is given.

    Returns:
        What the enrichment produced.

    Raises:
        EnrichmentError: If the document cannot be read, or a pass returns
            something that does not validate. Nothing is written.
        PromptError: If a prompt template is missing or does not match what
            fills it.
        sqlite3.Error: If the write fails. The transaction is rolled back
            first, so the document is left unenriched rather than half
            enriched.
    """
    document = read_document(connection, document_id)
    summary = passes.summarize(client, model, document)
    topics = passes.choose_topics(client, model, document, list_categories(connection))
    priority = passes.assess_priority(client, model, document)

    with connection:
        _write_summary(connection, document, summary, priority)
        _write_summary_chunk(connection, document.id, summary)
        filed = assign_topics(connection, document.id, topics)
        embedded = embed_document(
            connection,
            document.id,
            recompute=recompute_embeddings,
            embed=embed,
            model_id=embedding_model_id,
        )

    return Enriched(
        document_id=document.id,
        slug=document.slug,
        summary=summary,
        topics=tuple(filed),
        time_sensitivity=priority.time_sensitivity,
        business_impact=priority.business_impact,
        embedded=embedded,
    )


def enrich_documents(
    connection: sqlite3.Connection,
    client: object,
    model: str,
    document_ids: Sequence[int],
    recompute_embeddings: bool = False,
    embed: Embed | None = None,
    embedding_model_id: str | None = None,
) -> tuple[list[Enriched], list[Failure]]:
    """Enrich several documents, in order, one transaction each.

    Args:
        connection: An open document store.
        client: A configured client.
        model: The model id to call.
        document_ids: The documents to enrich, in the order to enrich them.
        recompute_embeddings: Re-embed chunks that already have a vector.
        embed: What to embed with. Defaults to the project's embedder.
        embedding_model_id: What to record as having produced the vectors.

    Returns:
        What was enriched, and one entry per document that could not be. A
        failure stops that document and nothing else: the ones before it
        stay written, and the ones after it are still attempted.
    """
    done: list[Enriched] = []
    failures: list[Failure] = []
    for document_id in document_ids:
        try:
            done.append(
                enrich_document(
                    connection,
                    client,
                    model,
                    document_id,
                    recompute_embeddings=recompute_embeddings,
                    embed=embed,
                    embedding_model_id=embedding_model_id,
                )
            )
        except (EnrichmentError, PromptError, sqlite3.Error, ValueError) as exc:
            failures.append(
                Failure(
                    document_id=document_id,
                    slug=_slug(connection, document_id),
                    error=exc,
                )
            )
    return done, failures


def dedupe_categories(
    connection: sqlite3.Connection, client: object, model: str
) -> list[Merged]:
    """Merge near-duplicate categories, once, over the finished list.

    Args:
        connection: An open document store.
        client: A configured client.
        model: The model id to call.

    Returns:
        What each merge did. Empty when the pass found nothing to merge, or
        when there are no categories to look at.

    Raises:
        EnrichmentError: If the response does not validate, or names a
            category that is not in the store. Nothing is merged.
        PromptError: If the prompt template is missing or does not match
            what fills it.
    """
    categories = list_categories(connection)
    if not categories:
        return []
    merges = passes.propose_merges(client, model, categories)
    with connection:
        return apply_merges(connection, merges)


def _write_summary(
    connection: sqlite3.Connection,
    document: StoredDocument,
    summary: str,
    priority: PriorityAssessment,
) -> None:
    """Write a document's summary and its two priority fields.

    Args:
        connection: An open document store.
        document: The document being enriched.
        summary: Its summary.
        priority: Its assessed time sensitivity and business impact.
    """
    connection.execute(
        """
        UPDATE documents
        SET summary = ?, time_sensitivity = ?, business_impact = ?
        WHERE id = ?
        """,
        (
            summary,
            priority.time_sensitivity,
            priority.business_impact,
            document.id,
        ),
    )


def _write_summary_chunk(
    connection: sqlite3.Connection, document_id: int, summary: str
) -> int:
    """Write the summary as a chunk of its own.

    A question about a whole document — what it was about, what it settled —
    has nothing to match in any single window of it. The summary chunk is
    what it matches. It is indexed and embedded like any other chunk, and
    carries no span, because it is written about the document rather than
    taken from a part of it.

    Any summary chunk from an earlier enrichment is deleted first, so
    re-running replaces it instead of leaving two.

    Args:
        connection: An open document store.
        document_id: The document the summary belongs to.
        summary: The summary text.

    Returns:
        The new chunk's id.
    """
    connection.execute(
        "DELETE FROM chunks WHERE document_id = ? AND kind = ?",
        (document_id, SUMMARY),
    )
    (highest,) = connection.execute(
        "SELECT max(ordinal) FROM chunks WHERE document_id = ?", (document_id,)
    ).fetchone()
    cursor = connection.execute(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, word_count, location,
             span_start, span_end, kind)
        VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)
        """,
        (
            document_id,
            0 if highest is None else highest + 1,
            summary,
            count_words(summary),
            SUMMARY_LOCATION,
            SUMMARY,
        ),
    )
    return cursor.lastrowid


def _slug(connection: sqlite3.Connection, document_id: int) -> str:
    """Return a document's slug, for a message about it.

    Args:
        connection: An open document store.
        document_id: The document.

    Returns:
        Its slug, or a stand-in naming the id when there is no such
        document — which is itself one of the failures this reports.
    """
    row = connection.execute(
        "SELECT slug FROM documents WHERE id = ?", (document_id,)
    ).fetchone()
    return row["slug"] if row is not None else f"document {document_id}"
