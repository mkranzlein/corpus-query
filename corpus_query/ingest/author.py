"""Resolving a document's author against the staff roster.

Word, PowerPoint, and Excel each carry an author in their core properties,
and each has to resolve that name to one person on the roster before the
document can be attributed to anyone. A name that matches nobody is worse
than no name at all, so a document whose author cannot be resolved is
reported unreadable rather than attributed to whatever string sat in the
file's metadata.

One function does this for all three formats, so a workbook whose author is
``jamal`` is accepted exactly where a deck's or a document's would be.
"""

from __future__ import annotations

from pathlib import Path

from corpus_query.ingest.reader import IngestError
from corpus_query.transcripts.roster import (
    ROSTER_PATH,
    RosterError,
    find_person,
    read_roster,
)

__all__ = ["ROSTER_PATH", "resolve_author"]


def resolve_author(
    path: Path, author: str | None, roster_path: Path | str = ROSTER_PATH
) -> str:
    """Resolve a document's author to one person on the roster.

    Args:
        path: The file, for the error messages.
        author: The author named in the file's core properties.
        roster_path: The roster to resolve against.

    Returns:
        The author's name, spelled the way the roster spells it.

    Raises:
        IngestError: If the author is blank, is not on the roster, or the
            roster cannot be read.
    """
    name = (author or "").strip()
    if not name:
        raise IngestError(f"{path} names no author in its core properties.")
    try:
        roster = read_roster(roster_path)
    except RosterError as exc:
        raise IngestError(
            f"Could not check {path}'s author against the roster: {exc}"
        ) from exc
    person = find_person(roster, name)
    if person is not None:
        return person.first_name
    known = ", ".join(person.first_name for person in roster)
    raise IngestError(
        f"{path} names {name!r} as its author, who is not on the roster at "
        f"{roster_path}. The roster has {known}."
    )
