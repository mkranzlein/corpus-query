"""Filling ``chunks.embedding``.

Chunks are passages, so they are embedded through
:func:`~corpus_query.models.embedder.embed_documents` — bare, with no
instruction prefix. The prefix belongs to the query side of the search, and
applying it here would still produce vectors, just ones that retrieve worse,
with nothing anywhere reporting a problem.

The model identifier and the dimensionality travel with every vector. A later
change of embedder then shows up as rows disagreeing about which model wrote
them, rather than as two vector spaces quietly mixed in one index.

Importing :mod:`corpus_query.models.embedder` pulls in torch, which is an
optional extra. It is imported when an embedding is actually computed rather
than at module import, so the rest of enrichment — and every test that
supplies its own embedding function — runs without the extra installed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from corpus_query.retrieval.blobs import vector_to_blob

#: Embeds passages: takes their text, returns one vector per text, in order.
type Embed = Callable[[Sequence[str]], np.ndarray]


@dataclass(frozen=True)
class Embedded:
    """What embedding one document's chunks did."""

    written: int
    """Chunks that were given an embedding."""

    skipped: int
    """Chunks left alone because they already had one."""

    model_id: str | None
    """What produced the vectors, or ``None`` when none were computed."""

    dimension: int | None
    """How long each vector is, or ``None`` when none were computed."""


def embed_document(
    connection: sqlite3.Connection,
    document_id: int,
    recompute: bool = False,
    embed: Embed | None = None,
    model_id: str | None = None,
) -> Embedded:
    """Embed a document's chunks, summary chunk included.

    Args:
        connection: An open document store.
        document_id: The document whose chunks to embed.
        recompute: Embed every chunk, including ones that already have a
            vector. Off by default: re-running enrichment should not pay to
            recompute what it computed last time.
        embed: What to embed with. Defaults to the project's embedder.
            Overridable so a test, or a future second embedder, can stand in
            for it.
        model_id: What to record as having produced the vectors. Defaults to
            the project embedder's identifier, and has to be given when
            ``embed`` is.

    Returns:
        What the pass did.

    Raises:
        ValueError: If ``embed`` is given without ``model_id``. A vector
            recorded against the wrong model is worse than no vector: it
            cannot be told apart from one the real embedder wrote.
    """
    if embed is not None and model_id is None:
        raise ValueError(
            "model_id has to be given alongside embed, so the vectors are "
            "recorded against what actually produced them."
        )
    rows = _chunks_to_embed(connection, document_id, recompute)
    skipped = _chunk_count(connection, document_id) - len(rows)
    if not rows:
        return Embedded(written=0, skipped=skipped, model_id=None, dimension=None)

    if embed is None:
        embed, model_id = _project_embedder()
    vectors = np.asarray(embed([row["text"] for row in rows]))
    if len(vectors) != len(rows):
        raise ValueError(
            f"The embedder returned {len(vectors)} vectors for {len(rows)} chunks."
        )

    dimension = int(vectors.shape[1])
    connection.executemany(
        """
        UPDATE chunks
        SET embedding = ?, embedding_model = ?, embedding_dim = ?
        WHERE id = ?
        """,
        [
            (vector_to_blob(vector), model_id, dimension, row["id"])
            for row, vector in zip(rows, vectors, strict=True)
        ],
    )
    return Embedded(
        written=len(rows), skipped=skipped, model_id=model_id, dimension=dimension
    )


def _project_embedder() -> tuple[Embed, str]:
    """Return the project's embedder and the identifier to record with it.

    Returns:
        The passage-side embedding function, and the model id it belongs to.
    """
    from corpus_query.models.embedder import EMBEDDING_MODEL_ID, embed_documents

    return embed_documents, EMBEDDING_MODEL_ID


def _chunks_to_embed(
    connection: sqlite3.Connection, document_id: int, recompute: bool
) -> list[sqlite3.Row]:
    """Return the chunks this pass should embed.

    Args:
        connection: An open document store.
        document_id: The document whose chunks to look at.
        recompute: Whether chunks that already have a vector are included.

    Returns:
        One row per chunk to embed, in document order.
    """
    query = "SELECT id, text FROM chunks WHERE document_id = ?"
    if not recompute:
        query += " AND embedding IS NULL"
    return connection.execute(f"{query} ORDER BY ordinal", (document_id,)).fetchall()


def _chunk_count(connection: sqlite3.Connection, document_id: int) -> int:
    """Count a document's chunks.

    Args:
        connection: An open document store.
        document_id: The document.

    Returns:
        How many chunks it has.
    """
    (count,) = connection.execute(
        "SELECT count(*) FROM chunks WHERE document_id = ?", (document_id,)
    ).fetchone()
    return count
