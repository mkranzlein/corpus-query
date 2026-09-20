"""The shape of one generated meeting.

These models do double duty. They are the structured-output type a model is
asked to fill, so the field descriptions are part of the prompt in every
practical sense, and they are the validation gate a response has to pass
before anything is written to disk.

Constraints are expressed as validators rather than as JSON Schema keywords
such as ``minLength``, because strict structured output supports only a
subset of that vocabulary. A validator says the same thing and is enforced on
our side either way.

Every piece of free text is normalized onto a single line as it is validated.
That is what lets the renderer write a turn as one line and mean it: a turn
holding an embedded newline never reaches the renderer, because validation
collapsed it first.
"""

from __future__ import annotations

import datetime
import re

from pydantic import BaseModel, Field, field_validator, model_validator

_WHITESPACE = re.compile(r"\s+")

#: Character that would make a rendered speaker marker ambiguous.
SPEAKER_MARKER_CLOSE = "]"


def normalize_line(text: str) -> str:
    """Collapse a string onto a single line.

    Args:
        text: The text to normalize.

    Returns:
        The text with every run of whitespace, newlines included, replaced by
        one space, and with the ends trimmed.
    """
    return _WHITESPACE.sub(" ", text).strip()


def _require_line(value: str, what: str) -> str:
    """Return ``value`` normalized onto one line, if it has any text at all.

    Args:
        value: The candidate string.
        what: Name of the thing being checked, for the error message.

    Returns:
        The normalized value.

    Raises:
        ValueError: If the value is empty or only whitespace.
    """
    line = normalize_line(value)
    if not line:
        raise ValueError(f"{what} must not be empty")
    return line


def _require_name(value: str, what: str) -> str:
    """Return a first name normalized onto one line.

    Args:
        value: The candidate name.
        what: Name of the field being checked, for the error message.

    Returns:
        The normalized name.

    Raises:
        ValueError: If the name is empty, or holds the character that closes
            a rendered speaker marker.
    """
    name = _require_line(value, what)
    if SPEAKER_MARKER_CLOSE in name:
        raise ValueError(
            f"{what} must not contain {SPEAKER_MARKER_CLOSE!r}, which would "
            f"make the rendered speaker marker ambiguous"
        )
    return name


class Turn(BaseModel):
    """One thing one person said."""

    speaker: str = Field(
        description="First name of the person speaking, from the roster."
    )
    text: str = Field(description="What the speaker said, in their own voice.")

    @field_validator("speaker")
    @classmethod
    def _check_speaker(cls, value: str) -> str:
        """Reject an unattributed turn, and a name that breaks the marker."""
        return _require_name(value, "speaker")

    @field_validator("text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        """Reject a turn that says nothing, and flatten one that spans lines."""
        return _require_line(value, "text")


class ActionItem(BaseModel):
    """Something one person left the meeting owing."""

    assignee: str = Field(
        description="First name of the person who owns the task, from the roster."
    )
    task: str = Field(description="What they agreed to do, in one sentence.")

    @field_validator("assignee")
    @classmethod
    def _check_assignee(cls, value: str) -> str:
        """Reject an unowned action item."""
        return _require_name(value, "assignee")

    @field_validator("task")
    @classmethod
    def _check_task(cls, value: str) -> str:
        """Reject an action item with no task."""
        return _require_line(value, "task")


class Meeting(BaseModel):
    """One meeting, as a record rather than as a document.

    An attendee who never takes a turn is allowed, as is an attendee who
    leaves with no action item: both are ordinary, and a corpus without them
    would be conspicuously tidy.
    """

    subject: str = Field(description="What the meeting was about, as a short title.")
    date: str = Field(description="The date the meeting happened, as YYYY-MM-DD.")
    attendees: list[str] = Field(
        description="First names of everyone present, from the roster."
    )
    turns: list[Turn] = Field(
        description="What was said, in order. Not everyone present has to speak."
    )
    decisions: list[str] = Field(
        description="What the meeting settled. May be empty if it settled nothing."
    )
    action_items: list[ActionItem] = Field(
        description=(
            "What people agreed to do afterwards. May be empty, and an "
            "attendee may own none."
        )
    )

    @field_validator("subject")
    @classmethod
    def _check_subject(cls, value: str) -> str:
        """Reject an untitled meeting."""
        return _require_line(value, "subject")

    @field_validator("date")
    @classmethod
    def _check_date(cls, value: str) -> str:
        """Reject anything that is not a calendar date in ISO order."""
        try:
            return datetime.date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            raise ValueError(
                f"date must be a calendar date written as YYYY-MM-DD, not {value!r}"
            ) from None

    @field_validator("attendees")
    @classmethod
    def _check_attendees(cls, value: list[str]) -> list[str]:
        """Reject an empty or duplicated attendee list."""
        attendees = [_require_name(name, "attendee") for name in value]
        if not attendees:
            raise ValueError("a meeting needs at least one attendee")
        if len(set(attendees)) != len(attendees):
            raise ValueError("an attendee is listed more than once")
        return attendees

    @field_validator("turns")
    @classmethod
    def _check_turns(cls, value: list[Turn]) -> list[Turn]:
        """Reject a meeting in which nobody says anything."""
        if not value:
            raise ValueError("a meeting needs at least one turn")
        return value

    @field_validator("decisions")
    @classmethod
    def _check_decisions(cls, value: list[str]) -> list[str]:
        """Reject a blank entry in an otherwise fine list of decisions."""
        return [_require_line(decision, "decision") for decision in value]

    @model_validator(mode="after")
    def _check_everyone_named_was_there(self) -> Meeting:
        """Reject a meeting that names someone who was not present.

        A speaker who does not attend, or an action item owned by someone who
        was not in the room, is the kind of quiet inconsistency generation
        produces and a reader would notice. The attendee list is taken as the
        authority, since it is the meeting's own account of who was there.

        Returns:
            The meeting, unchanged.

        Raises:
            ValueError: If a turn or an action item names someone who is not
                an attendee.
        """
        present = set(self.attendees)
        strangers = {turn.speaker for turn in self.turns} - present
        if strangers:
            raise ValueError(
                f"{', '.join(sorted(strangers))} speaks but is not an attendee"
            )
        unassigned = {item.assignee for item in self.action_items} - present
        if unassigned:
            raise ValueError(
                f"{', '.join(sorted(unassigned))} owns an action item but is "
                f"not an attendee"
            )
        return self


type Meetings = list[Meeting]
"""Every meeting from one generation request.

Naming the shape gives the generator something to hand to a structured-output
call, and something to validate a response against, without spelling the list
out at each call site.
"""
