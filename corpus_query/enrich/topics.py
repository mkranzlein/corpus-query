"""The category list, and what documents are filed under it.

Categories live in ``topics``; the filing lives in ``document_topics``. Both
are written here, so there is one place that knows a category is matched
without regard to case — "Supply chain" arriving for a list that already
holds "Supply Chain" is the same category spelled carelessly, and creating a
second row for it is how a category list quietly fragments.

Documents are enriched one at a time, in sequence, for the same reason: each
pass is shown the categories every earlier pass created, so the list
converges instead of growing a private vocabulary per document.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

from corpus_query.enrich.errors import EnrichmentError

#: Where the seed category list lives, relative to the repository root.
#: Markdown rather than a machine-readable format, like the roster, because
#: it is also meant to be read and edited by a person.
DEFAULT_TOPICS_FILE = Path("data/topics.md")

#: Stand-in for the category list when there is nothing in it yet.
NO_CATEGORIES = "None yet. Name the categories this meeting needs."

_BULLET = "- "


def read_seed_topics(path: Path | str = DEFAULT_TOPICS_FILE) -> tuple[str, ...]:
    """Read the seeded starting category list.

    Args:
        path: Path to the seed list.

    Returns:
        The category names, in the order the file lists them.

    Raises:
        EnrichmentError: If the file cannot be read, lists no categories, or
            lists one twice.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EnrichmentError(
            f"Could not read the seed categories at {path}: {exc}"
        ) from exc

    names = [
        line.strip().removeprefix(_BULLET).strip()
        for line in text.splitlines()
        if line.strip().startswith(_BULLET)
    ]
    if not names:
        raise EnrichmentError(f"{path} lists no categories.")
    if len({name.casefold() for name in names}) != len(names):
        raise EnrichmentError(f"{path} lists the same category more than once.")
    return tuple(names)


def seed_categories(connection: sqlite3.Connection, names: Iterable[str]) -> list[str]:
    """Add the seed categories that are not in the store yet.

    Args:
        connection: An open document store.
        names: The seed category names.

    Returns:
        The names this call added, in the order they were given. Empty when
        the store already held all of them, which is the normal case on
        every run after the first.
    """
    existing = {name.casefold() for name in list_categories(connection)}
    added = [name for name in names if name.casefold() not in existing]
    connection.executemany(
        "INSERT INTO topics (name) VALUES (?)", [(name,) for name in added]
    )
    return added


def list_categories(connection: sqlite3.Connection) -> list[str]:
    """Return every category name in the store.

    Args:
        connection: An open document store.

    Returns:
        The names, in alphabetical order, which is the order a prompt should
        see them in: stable between runs and independent of what was created
        when.
    """
    return [
        row["name"]
        for row in connection.execute("SELECT name FROM topics ORDER BY name")
    ]


def describe_categories(names: Sequence[str]) -> str:
    """Render the category list for a prompt.

    Args:
        names: The category names.

    Returns:
        One bullet per category, or a line saying there are none.
    """
    if not names:
        return NO_CATEGORIES
    return "\n".join(f"{_BULLET}{name}" for name in names)


def assign_topics(
    connection: sqlite3.Connection, document_id: int, names: Sequence[str]
) -> list[str]:
    """File one document under the categories a pass chose for it.

    A name that matches an existing category, ignoring case, files the
    document under that category rather than creating a second one. A name
    that matches nothing creates a category, which is how the list grows.

    Whatever the document was filed under before is cleared first, so
    re-enriching a document replaces its topics instead of adding to them.

    Args:
        connection: An open document store.
        document_id: The document being filed.
        names: The category names the pass chose.

    Returns:
        The names the document is now filed under, in the store's own
        spelling of them.
    """
    connection.execute(
        "DELETE FROM document_topics WHERE document_id = ?", (document_id,)
    )
    filed = []
    for name in names:
        topic_id, stored = _category(connection, name)
        connection.execute(
            "INSERT OR IGNORE INTO document_topics (document_id, topic_id) "
            "VALUES (?, ?)",
            (document_id, topic_id),
        )
        filed.append(stored)
    return filed


def _category(connection: sqlite3.Connection, name: str) -> tuple[int, str]:
    """Return a category's id and stored name, creating it if it is new.

    Args:
        connection: An open document store.
        name: The category name, in whatever spelling the pass returned.

    Returns:
        The category's id, and the name as the store holds it.
    """
    row = connection.execute(
        "SELECT id, name FROM topics WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if row is not None:
        return row["id"], row["name"]
    cursor = connection.execute("INSERT INTO topics (name) VALUES (?)", (name,))
    return cursor.lastrowid, name
