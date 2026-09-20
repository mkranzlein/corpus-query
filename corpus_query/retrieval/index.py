"""Building and opening the Chroma vector index.

The index is a cache, not a source of truth. The embeddings already sitting
in ``chunks.embedding`` are what got shipped; this module turns them into
something dense search can run against, and rebuilds that from scratch
whenever it looks stale or is simply not there yet. Nothing here re-embeds a
chunk — a missing embedding means the chunk is skipped, not computed.

A chunk's row id doubles as its vector id, so a dense hit maps straight back
to a row with no lookup table in between.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from corpus_query.retrieval.blobs import blob_to_vector

#: Where the index lives, relative to the repository root. Gitignored and
#: rebuilt on demand; see the module docstring.
DEFAULT_INDEX_DIR = Path(".cache") / "chroma"

#: Name of the single collection this module manages.
COLLECTION_NAME = "chunks"

#: bge embeddings are trained for cosine similarity, not Chroma's default
#: (squared L2), so the collection is configured to match.
_COLLECTION_METADATA = {"hnsw:space": "cosine"}


def open_index(
    connection: sqlite3.Connection, path: Path | str = DEFAULT_INDEX_DIR
) -> Collection:
    """Open the vector index, rebuilding it if it is missing or stale.

    "Stale" is judged by count alone: the index disagrees with the number of
    chunks that currently have an embedding. That catches an index left over
    from before a re-ingest, or one that was never built, without needing to
    compare every vector.

    Args:
        connection: An open document store to check the index against, and
            to rebuild from if needed.
        path: Where the index lives on disk.

    Returns:
        The open collection, guaranteed to hold exactly one vector per
        embedded chunk.
    """
    client = chromadb.PersistentClient(path=str(path))
    expected = _count_embedded_chunks(connection)
    collection = _get_or_create(client)
    if collection.count() != expected:
        collection = _rebuild(client, connection)
    return collection


def build_index(
    connection: sqlite3.Connection, path: Path | str = DEFAULT_INDEX_DIR
) -> Collection:
    """Rebuild the vector index from ``chunks.embedding``, unconditionally.

    The collection is dropped and recreated rather than upserted into, so
    running this twice — or running it after chunks were deleted or
    replaced — leaves exactly the vectors the store currently has, never a
    duplicate or a leftover from a chunk that no longer exists.

    Args:
        connection: An open document store to rebuild the index from.
        path: Where the index lives on disk.

    Returns:
        The freshly built collection.
    """
    client = chromadb.PersistentClient(path=str(path))
    return _rebuild(client, connection)


def _rebuild(client: chromadb.ClientAPI, connection: sqlite3.Connection) -> Collection:
    """Drop and recreate the collection, then repopulate it.

    Args:
        client: An open Chroma client.
        connection: An open document store.

    Returns:
        The rebuilt collection.
    """
    try:
        client.delete_collection(COLLECTION_NAME)
    except chromadb.errors.NotFoundError:
        pass
    collection = _get_or_create(client)
    rows = connection.execute(
        "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL"
    ).fetchall()
    if rows:
        collection.add(
            ids=[str(row["id"]) for row in rows],
            embeddings=[blob_to_vector(row["embedding"]).tolist() for row in rows],
        )
    return collection


def _get_or_create(client: chromadb.ClientAPI) -> Collection:
    """Open the collection this module manages, creating it if needed.

    Args:
        client: An open Chroma client.

    Returns:
        The collection, configured for cosine similarity.
    """
    return client.get_or_create_collection(
        COLLECTION_NAME, metadata=_COLLECTION_METADATA
    )


def _count_embedded_chunks(connection: sqlite3.Connection) -> int:
    """Count chunks that have an embedding to index.

    Args:
        connection: An open document store.

    Returns:
        The number of chunks with a non-null ``embedding``.
    """
    (count,) = connection.execute(
        "SELECT count(*) FROM chunks WHERE embedding IS NOT NULL"
    ).fetchone()
    return count
