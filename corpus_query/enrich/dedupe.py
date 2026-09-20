"""Folding near-duplicate categories back together.

Documents are filed one at a time, so the category list drifts: the third
meeting about a late supplier is filed under "Supply Chain Risk" because
nothing on the list that day said "Supply Chain" clearly enough. This pass
runs once, over the finished list, and merges the pairs that mean the same
thing.

The repointing is the part worth reading carefully. ``document_topics`` has
``(document_id, topic_id)`` as its primary key, and a document filed under
both the merged name and the surviving one already holds the row the merge
would create. Updating its topic_id would collide, so the update skips those
rows and they are deleted instead — the document keeps exactly one row for
the surviving category either way.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from corpus_query.enrich.errors import EnrichmentError
from corpus_query.enrich.schema import TopicMerge


@dataclass(frozen=True)
class Merged:
    """What merging one group of categories did."""

    keep: str
    """The surviving category's name, as the store holds it."""

    merged: tuple[str, ...]
    """The names that were folded into it and no longer exist."""

    repointed: int
    """Document filings moved onto the surviving category."""

    collapsed: int
    """Filings dropped because the document already held both categories."""


def apply_merges(
    connection: sqlite3.Connection, merges: Sequence[TopicMerge]
) -> list[Merged]:
    """Merge each proposed group of categories into one.

    Args:
        connection: An open document store.
        merges: The groups the dedupe pass proposed.

    Returns:
        What each merge did, in the order the merges were given.

    Raises:
        EnrichmentError: If a merge names a category that is not in the
            store, or names the same category in two groups. Nothing is
            written in that case: a proposal that does not match the list it
            was shown is not one to apply half of.
    """
    _check(connection, merges)
    return [_apply(connection, merge) for merge in merges]


def _check(connection: sqlite3.Connection, merges: Sequence[TopicMerge]) -> None:
    """Reject a proposal before any of it is applied.

    Args:
        connection: An open document store.
        merges: The proposed groups.

    Raises:
        EnrichmentError: If a name is unknown, or appears in two groups.
    """
    known = {name.casefold() for name in _names(connection)}
    seen: set[str] = set()
    for merge in merges:
        for name in (merge.keep, *merge.merge):
            folded = name.casefold()
            if folded not in known:
                raise EnrichmentError(
                    f"The dedupe pass named {name!r}, which is not a category "
                    f"in the store. Nothing was merged."
                )
            if folded in seen:
                raise EnrichmentError(
                    f"The dedupe pass named {name!r} in more than one merge. "
                    f"Nothing was merged."
                )
            seen.add(folded)


def _apply(connection: sqlite3.Connection, merge: TopicMerge) -> Merged:
    """Carry out one merge.

    Args:
        connection: An open document store.
        merge: The group to merge.

    Returns:
        What the merge did.
    """
    keep_id, keep_name = _lookup(connection, merge.keep)
    merged, repointed, collapsed = [], 0, 0
    for name in merge.merge:
        topic_id, stored = _lookup(connection, name)
        moved, dropped = _repoint(connection, topic_id, keep_id)
        connection.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        merged.append(stored)
        repointed += moved
        collapsed += dropped
    return Merged(
        keep=keep_name,
        merged=tuple(merged),
        repointed=repointed,
        collapsed=collapsed,
    )


def _repoint(
    connection: sqlite3.Connection, topic_id: int, keep_id: int
) -> tuple[int, int]:
    """Move a category's filings onto the surviving category.

    ``UPDATE OR IGNORE`` is what handles a document that is already filed
    under both: the row that would collide with the one it already has is
    left where it is rather than failing the statement, and is then deleted.
    Without that, every such document would abort the merge.

    Args:
        connection: An open document store.
        topic_id: The category being merged away.
        keep_id: The category that survives.

    Returns:
        How many filings were moved, and how many were dropped as duplicates
        of one the document already had.
    """
    before = _filings(connection, topic_id)
    moved = connection.execute(
        "UPDATE OR IGNORE document_topics SET topic_id = ? WHERE topic_id = ?",
        (keep_id, topic_id),
    ).rowcount
    connection.execute("DELETE FROM document_topics WHERE topic_id = ?", (topic_id,))
    return moved, before - moved


def _filings(connection: sqlite3.Connection, topic_id: int) -> int:
    """Count the documents filed under a category.

    Args:
        connection: An open document store.
        topic_id: The category.

    Returns:
        How many documents are filed under it.
    """
    (count,) = connection.execute(
        "SELECT count(*) FROM document_topics WHERE topic_id = ?", (topic_id,)
    ).fetchone()
    return count


def _lookup(connection: sqlite3.Connection, name: str) -> tuple[int, str]:
    """Return a category's id and stored name.

    Args:
        connection: An open document store.
        name: The category name, matched without regard to case.

    Returns:
        The id, and the name as the store holds it.

    Raises:
        EnrichmentError: If there is no such category. :func:`_check` has
            already ruled this out for a proposal being applied; it is here
            so the function cannot silently return something wrong if it is
            ever called on its own.
    """
    row = connection.execute(
        "SELECT id, name FROM topics WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if row is None:
        raise EnrichmentError(f"There is no category named {name!r}.")
    return row["id"], row["name"]


def _names(connection: sqlite3.Connection) -> list[str]:
    """Return every category name in the store.

    Args:
        connection: An open document store.

    Returns:
        The names, in no particular order.
    """
    return [row["name"] for row in connection.execute("SELECT name FROM topics")]
