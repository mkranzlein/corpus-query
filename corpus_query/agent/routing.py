"""Turning an abstention into a suggestion of who to ask.

When the record does not settle a question, the passages retrieved while
trying are not worthless. Each one names the person who wrote it or the
people who were in the room, so the material that scored well without
answering the question already points at who would know. This module reads
that pointer: it ranks the people the retrieved passages name, resolves them
against the roster, and keeps the passages that named each one so a
suggestion can be followed back the same way a claim can.

Two rules keep a suggestion honest. A person is only suggested if the roster
has them, so what comes back is a colleague rather than whatever string sat
in a file's properties. And the evidence for a suggestion is the citation
itself — document, date, author or attendees, location — rather than a
paraphrase of why they seem relevant.

Nothing here sends anything. The drafted question is text for the user to
edit, and this module hands it back with the answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

from corpus_query.transcripts.roster import (
    ROSTER_PATH,
    Person,
    RosterError,
    find_person,
    read_roster,
)

#: How many people one suggestion names. A meeting puts everyone who was in
#: the room on every passage it produced, so an uncapped list is most of the
#: company ranked by who attends the most meetings. Three is a suggestion; a
#: ranked ten is a directory.
MAX_CANDIDATES = 3

#: What the routing model says when the answer settled the question. A word
#: rather than a JSON object because it is the whole reply: the model either
#: says this or writes the question to forward.
ANSWERED = "ANSWERED"


@dataclass(frozen=True)
class Candidate:
    """One person worth asking, and what named them."""

    person: Person
    """Who to ask, as the roster spells them."""

    evidence: list[dict[str, Any]]
    """The retrieved passages this person wrote or attended, best first and
    cited the way an answer's claims are cited."""

    def as_dict(self) -> dict[str, Any]:
        """Render the candidate as plain data.

        Graph state is checkpointed, so what travels in it is dicts and
        strings rather than dataclasses that a later version might rename.

        Returns:
            The person, their role and department, how many passages named
            them, and those passages.
        """
        return {
            "name": self.person.first_name,
            "role": self.person.role,
            "department": self.person.department,
            "passages": len(self.evidence),
            "evidence": self.evidence,
        }


def people_named(citation: dict[str, Any]) -> list[str]:
    """Return the people one passage names.

    Args:
        citation: One citation, as :func:`corpus_query.agent.retrieval.citation`
            builds it.

    Returns:
        The author, for a document that has one; everyone who was in the
        room, for a meeting; nothing for a passage that names neither.
    """
    author = (citation.get("author") or "").strip()
    if author:
        return [author]
    return [name for name in (citation.get("attendees") or []) if name.strip()]


def candidates(
    citations: list[dict[str, Any]],
    roster: tuple[Person, ...] | None = None,
    limit: int = MAX_CANDIDATES,
) -> list[Candidate]:
    """Rank the people the retrieved passages name.

    The ranking is by how much of the matched material each person wrote or
    attended — one passage, one count — and ties go to whoever appeared in a
    better-ranked passage first, since the citations arrive best first.

    Args:
        citations: The passages this turn retrieved, best first.
        roster: Who exists. Read from the project's roster when not given.
        limit: How many people to suggest at most.

    Returns:
        The best candidates, best first. Empty when nothing was retrieved,
        when the passages name nobody, or when no name they carry is on the
        roster.
    """
    people = roster if roster is not None else load_roster()
    if not people:
        return []

    evidence: dict[str, list[dict[str, Any]]] = {}
    resolved: dict[str, Person] = {}
    for entry in citations:
        for name in people_named(entry):
            person = find_person(people, name)
            if person is None:
                continue
            resolved.setdefault(person.first_name, person)
            evidence.setdefault(person.first_name, []).append(entry)

    ranked = sorted(evidence, key=lambda name: -len(evidence[name]))
    return [
        Candidate(person=resolved[name], evidence=evidence[name])
        for name in ranked[:limit]
    ]


def drafted_question(reply: str) -> str | None:
    """Read the routing model's reply.

    The reply is either the sentinel or two labelled lines: the context that
    made the question unanswerable, and the question itself. The labels are
    there because a small model asked in prose for "context and then the
    question" reliably writes the question alone, and asked for the same two
    things under two labels reliably writes both. They are stripped here, so
    what the user is handed is prose rather than a form.

    Args:
        reply: What the model said when it was shown the question and the
            answer that came back.

    Returns:
        The question to forward, or ``None`` if the model judged that the
        answer settled the question — which is also what an empty reply is
        taken to mean, since a suggestion nobody can read is worse than no
        suggestion. A reply that arrives without the labels is passed
        through as written: it is a question that lost its context, which is
        still worth forwarding.
    """
    text = reply.strip()
    if not text:
        return None
    if _sentinel(text.splitlines()[0]):
        return None
    parts = [_unlabelled(line) for line in text.splitlines() if line.strip()]
    return " ".join(part for part in parts if part)


def _sentinel(line: str) -> bool:
    """Return whether a line is the model saying the question was answered.

    Args:
        line: The reply's first line.

    Returns:
        Whether it is the sentinel, read through the emphasis and
        punctuation a small model puts around a word it was told to say on
        its own.
    """
    return line.strip().strip("*_#`.:!").upper() == ANSWERED


def _unlabelled(line: str) -> str:
    """Strip the ``CONTEXT:``/``QUESTION:`` label off one line.

    Args:
        line: One line of the reply.

    Returns:
        The line's prose, without the label the prompt asked for.
    """
    stripped = line.strip()
    label, separator, rest = stripped.partition(":")
    if separator and label.strip().strip("*_ ").upper() in {"CONTEXT", "QUESTION"}:
        return rest.strip()
    return stripped


def suggestion(
    citations: list[dict[str, Any]],
    reply: str,
    roster: tuple[Person, ...] | None = None,
) -> dict[str, Any] | None:
    """Build the routing a response carries, if there is one to build.

    Args:
        citations: The passages this turn retrieved, best first.
        reply: The routing model's reply.
        roster: Who exists. Read from the project's roster when not given.

    Returns:
        The candidates and the drafted question, as plain data — or
        ``None`` when the question was answered, or when the passages point
        at nobody to ask. A suggestion naming no one is not a suggestion.
    """
    question = drafted_question(reply)
    if question is None:
        return None
    people = candidates(citations, roster=roster)
    if not people:
        return None
    return {
        "candidates": [person.as_dict() for person in people],
        "question": question,
    }


@cache
def load_roster() -> tuple[Person, ...]:
    """Read the project's roster once, for the life of the process.

    The roster is a committed file that does not change while the service
    is running, and routing reads it on every abstention.

    Returns:
        Everyone on the roster, or nothing at all if it cannot be read. A
        suggestion is a convenience on top of an answer that has already
        been written, so a roster that will not load costs the suggestion
        rather than the answer.
    """
    try:
        return read_roster(ROSTER_PATH)
    except RosterError:
        return ()
