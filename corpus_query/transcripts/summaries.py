"""Reading what earlier batches already produced.

Generation is batched: a run asks for a handful of meetings, those meetings are
ingested, and the next run is told what the earlier ones were about so the
corpus does not collapse into twenty variations of the same status meeting.
What it is told comes from the ``documents`` table that ingestion fills.

A missing database is the normal case rather than an error — it is exactly what
the first batch sees, and the first batch has to work before ingestion exists
at all. So is a database that has no ``documents`` table yet. Both read as "no
prior meetings".

This module opens the database read-only and asks it one question. It is
deliberately the smallest read that answers it, so the generator does not wait
on the store. Once the store package lands, this should be reconciled with it
rather than kept as a second way of opening the same file.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

#: Where the document store is expected to live, relative to the repository
#: root.
DEFAULT_DATABASE_FILE = Path("data/corpus.db")

#: Stand-in for the summaries section when there are none.
NO_PRIOR_MEETINGS = "None yet. This is the first batch."

_QUERY = """
    SELECT subject, date, summary
    FROM documents
    WHERE summary IS NOT NULL AND TRIM(summary) <> ''
    ORDER BY date, subject
"""


@dataclass(frozen=True)
class PriorMeeting:
    """A meeting an earlier batch produced, as the prompt needs to see it."""

    subject: str
    date: str
    summary: str


def read_summaries(
    path: Path | str = DEFAULT_DATABASE_FILE,
) -> tuple[PriorMeeting, ...]:
    """Read the summaries of everything ingested so far.

    Args:
        path: Path to the document store.

    Returns:
        One entry per summarized document, oldest first. Empty when the
        database does not exist, has no ``documents`` table, or holds nothing
        that has been summarized yet.
    """
    path = Path(path)
    if not path.is_file():
        return ()
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            rows = connection.execute(_QUERY).fetchall()
    except sqlite3.Error:
        return ()
    return tuple(PriorMeeting(*row) for row in rows)


def describe_prior_meetings(meetings: tuple[PriorMeeting, ...]) -> str:
    """Render prior meetings for the prompt.

    Args:
        meetings: What earlier batches produced.

    Returns:
        One paragraph per meeting, or a line saying there are none.
    """
    if not meetings:
        return NO_PRIOR_MEETINGS
    return "\n\n".join(
        f"- **{meeting.subject}** ({meeting.date}) — {meeting.summary}"
        for meeting in meetings
    )
