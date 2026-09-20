"""Reading what earlier batches already produced.

Generation is batched: a run asks for a handful of meetings, those meetings are
ingested, and the next run is told what the earlier ones were about so the
corpus does not collapse into twenty variations of the same status meeting.
What it is told comes from the ``documents`` table that ingestion fills.

A missing database is the normal case rather than an error — it is exactly what
the first batch sees, and the first batch has to work before ingestion exists
at all. So is a database that exists but has not been brought up to schema
yet. Both read as "no prior meetings".

This module asks the store one question, through the same ``connect`` helper
everything else that opens the document store uses, so there is exactly one
place that knows how a document store is opened and what its columns are
named.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from corpus_query.store.db import DEFAULT_DATABASE_FILE, connect
from corpus_query.store.kinds import TRANSCRIPT

__all__ = [
    "DEFAULT_DATABASE_FILE",
    "NO_PRIOR_MEETINGS",
    "PriorMeeting",
    "describe_prior_meetings",
    "read_summaries",
]

#: Stand-in for the summaries section when there are none.
NO_PRIOR_MEETINGS = "None yet. This is the first batch."

#: Only transcripts. The generator is being told what meetings it has
#: already written, and a document of some other kind is not one of those,
#: however well it was summarized.
_QUERY = f"""
    SELECT title, document_date, summary
    FROM documents
    WHERE source_kind = '{TRANSCRIPT}'
      AND summary IS NOT NULL AND TRIM(summary) <> ''
    ORDER BY document_date, title
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
        database does not exist or has not been ingested into yet.

    Raises:
        SchemaVersionError: If the database's recorded schema version is not
            the one this code knows how to work with — a real incompatibility,
            not the normal "nothing ingested yet" case.
    """
    path = Path(path)
    if not path.is_file():
        return ()
    connection = connect(path)
    try:
        rows = connection.execute(_QUERY).fetchall()
    finally:
        connection.close()
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
