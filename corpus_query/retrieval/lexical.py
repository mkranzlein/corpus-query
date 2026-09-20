"""BM25 search over ``chunks_fts``.

A search query is prose typed by a person, not FTS5 syntax. FTS5 gives
meaning to `"`, `*`, `^`, `:`, and the bareword operators `AND`/`OR`/`NOT` —
passed straight through, a query that happens to contain any of those either
raises a syntax error or silently turns into a different search than the one
the user typed. This module never hands FTS5 anything but individually
quoted terms, so none of that syntax can reach it.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

#: A query term: a run of word characters or apostrophes. Everything else —
#: quotes, `*`, `^`, punctuation, whitespace — is a separator and never
#: reaches FTS5, which is what keeps FTS5 syntax out of a prose query.
_TERM_PATTERN = re.compile(r"[\w']+", re.UNICODE)


@dataclass(frozen=True)
class LexicalHit:
    """One chunk BM25 matched, and how well."""

    chunk_id: int
    score: float
    """Higher is better, matching the dense side. FTS5's own ``bm25()``
    returns lower-is-better, so this is its negation."""


def terms(query: str) -> list[str]:
    """Split a query into the terms it will be searched on.

    Args:
        query: The raw, unescaped user query.

    Returns:
        Its terms, lowercased, in order. Empty when the query holds no word
        characters at all.
    """
    return [term.lower() for term in _TERM_PATTERN.findall(query)]


def _quote(term: str) -> str:
    """Quote one term as an FTS5 string literal.

    Args:
        term: A single query term, already stripped of anything but word
            characters and apostrophes by :func:`terms`.

    Returns:
        The term as an FTS5 phrase, with any embedded double quote doubled
        per FTS5's escaping rule.
    """
    return f'"{term.replace(chr(34), chr(34) * 2)}"'


def _match_expression(query_terms: list[str]) -> str:
    """Build an FTS5 MATCH expression that finds a chunk matching any term.

    Terms are OR'd rather than AND'd: the point of the lexical half of
    retrieval is recall on a part number or a name, and OR-ing keeps a chunk
    that only shares one rare term with the query in the running, with BM25
    ranking it below a chunk that shares more.

    Args:
        query_terms: The terms to search for, as returned by :func:`terms`.

    Returns:
        An FTS5 MATCH expression built entirely from quoted terms.
    """
    return " OR ".join(_quote(term) for term in query_terms)


def search_lexical(
    connection: sqlite3.Connection, query: str, limit: int = 50
) -> list[LexicalHit]:
    """Rank chunks against a query with BM25.

    Args:
        connection: An open document store.
        query: The raw user query. Escaped before it reaches FTS5; see the
            module docstring.
        limit: The most hits to return.

    Returns:
        Hits ordered best first. Empty when the query holds no searchable
        term or when nothing matches — both ordinary outcomes, not errors.
    """
    query_terms = terms(query)
    if not query_terms:
        return []
    rows = connection.execute(
        """
        SELECT rowid AS chunk_id, bm25(chunks_fts) AS raw_score
        FROM chunks_fts
        WHERE chunks_fts MATCH ?
        ORDER BY raw_score
        LIMIT ?
        """,
        (_match_expression(query_terms), limit),
    ).fetchall()
    return [
        LexicalHit(chunk_id=row["chunk_id"], score=-row["raw_score"]) for row in rows
    ]


def unmatched_terms(connection: sqlite3.Connection, query: str) -> list[str]:
    """Return the query's terms that matched no chunk at all.

    Args:
        connection: An open document store.
        query: The raw user query.

    Returns:
        Terms, in query order, that FTS5 found nowhere in the corpus. A term
        here is a signal that the query named something the corpus does not
        have, such as a misspelled part number.
    """
    missing = []
    for term in terms(query):
        (count,) = connection.execute(
            "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            (_quote(term),),
        ).fetchone()
        if count == 0:
            missing.append(term)
    return missing
