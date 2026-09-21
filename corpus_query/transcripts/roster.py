"""Reading the staff roster that generated documents draw their cast from.

The roster is a markdown table in ``data/roster.md`` rather than a file in a
machine-readable format, because it is also meant to be read by a person. It
stays the single source of truth for who exists: code reads names from it
instead of carrying a copy of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Where the roster lives, relative to the repository root.
DEFAULT_ROSTER_FILE = Path("data/roster.md")

#: The same roster, resolved from the package's own location rather than the
#: working directory, so code that runs from anywhere still finds it.
ROSTER_PATH = Path(__file__).resolve().parents[2] / DEFAULT_ROSTER_FILE

_HEADER_FIRST_CELL = "first name"
_EXPECTED_CELLS = 3


class RosterError(Exception):
    """The roster file is missing, or is not shaped like a roster."""


@dataclass(frozen=True)
class Person:
    """One person on the staff roster."""

    first_name: str
    role: str
    department: str


def read_roster(path: Path | str = DEFAULT_ROSTER_FILE) -> tuple[Person, ...]:
    """Read the roster table.

    Args:
        path: Path to the roster markdown file.

    Returns:
        Everyone on the roster, in the order the table lists them.

    Raises:
        RosterError: If the file cannot be read, holds no table rows, has a
            row that is not three cells wide, or names the same person twice.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RosterError(f"Could not read the roster at {path}: {exc}") from exc

    people: list[Person] = []
    for line in text.splitlines():
        row = line.strip()
        if not row.startswith("|"):
            continue
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if _is_header(cells) or _is_separator(cells):
            continue
        if len(cells) != _EXPECTED_CELLS:
            raise RosterError(
                f"{path} has a row with {len(cells)} cells where three were "
                f"expected (first name, role, department): {row}"
            )
        people.append(Person(*cells))

    if not people:
        raise RosterError(f"{path} contains no roster rows.")
    names = [person.first_name for person in people]
    if len(set(names)) != len(names):
        raise RosterError(
            f"{path} lists the same first name more than once, so a name in a "
            f"document would not resolve to one person."
        )
    return tuple(people)


def find_person(people: tuple[Person, ...], name: str) -> Person | None:
    """Look one name up on the roster.

    Names reach this from a file's core properties, a transcript header, or
    a search result, so they are matched without regard to case. Nothing
    else is guessed at: a name that is not on the roster comes back as
    ``None`` rather than as the closest person to it.

    Args:
        people: The roster.
        name: The name to resolve.

    Returns:
        The person, spelled the way the roster spells them, or ``None`` if
        the roster does not have them.
    """
    wanted = name.strip().casefold()
    if not wanted:
        return None
    for person in people:
        if person.first_name.casefold() == wanted:
            return person
    return None


def first_names(people: tuple[Person, ...]) -> tuple[str, ...]:
    """Return just the first names, in roster order.

    Args:
        people: The roster.

    Returns:
        Each person's first name.
    """
    return tuple(person.first_name for person in people)


def describe_roster(people: tuple[Person, ...]) -> str:
    """Render the roster as one line per person.

    Args:
        people: The roster.

    Returns:
        One ``- Name (Role, Department)`` line per person.
    """
    return "\n".join(
        f"- {person.first_name} ({person.role}, {person.department})"
        for person in people
    )


def _is_header(cells: list[str]) -> bool:
    """Return whether a row is the table's header row."""
    return bool(cells) and cells[0].lower() == _HEADER_FIRST_CELL


def _is_separator(cells: list[str]) -> bool:
    """Return whether a row is the dashed rule under the header."""
    return all(cell and set(cell) <= set(":- ") for cell in cells)
