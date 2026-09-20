"""The shapes a model is asked to fill during enrichment.

Each pass asks for a structured response and validates it before anything is
written. The validators are the gate: a priority outside the fixed
vocabulary, a sixth topic, or a summary that is one sentence long is a
failed document rather than a row written with something nobody asked for.

The two priority fields are deliberately separate. A single blended
"priority" cannot distinguish a small decision that has to happen this week
from an expensive one with no deadline, and those are answered differently.
"""

from __future__ import annotations

import re
from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator

# Plain assignments rather than PEP 695 ``type`` aliases: pydantic renders a
# named alias as a ``$ref`` into ``$defs``, and an alias used once is clearer
# to a structured-output call when it is inlined as the enum it is.

#: How soon the document's subject matter needs attention.
TimeSensitivity = Literal["urgent", "near_term", "long_term", "none"]

#: How much of the business the document's subject matter moves.
BusinessImpact = Literal["critical", "significant", "moderate", "minor"]

#: The vocabularies as tuples, for the prompts and for anything checking a
#: value that did not come through pydantic. Derived from the types above so
#: there is one place a vocabulary is written down.
TIME_SENSITIVITY_VALUES: tuple[str, ...] = get_args(TimeSensitivity)
BUSINESS_IMPACT_VALUES: tuple[str, ...] = get_args(BusinessImpact)

#: Topics one document may carry. A document about everything is a document
#: about nothing, and the cap is what keeps the assignment a choice.
MAX_TOPICS = 5

#: Sentences a summary may run to, inclusive. Long enough to say what a
#: meeting settled, short enough that a prompt can carry twenty of them.
MIN_SUMMARY_SENTENCES = 2
MAX_SUMMARY_SENTENCES = 5

#: Longest a category name may be. A name past this is a description, and a
#: category list of descriptions stops being a category list.
MAX_TOPIC_CHARS = 60

_WHITESPACE = re.compile(r"\s+")

#: A sentence boundary: terminating punctuation followed by whitespace. Used
#: only to size a summary, where being off by one on an abbreviation costs a
#: retry rather than a wrong answer.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def normalize(text: str) -> str:
    """Collapse a string onto a single line.

    Args:
        text: The text to normalize.

    Returns:
        The text with every run of whitespace replaced by one space, and with
        the ends trimmed.
    """
    return _WHITESPACE.sub(" ", text).strip()


def count_sentences(text: str) -> int:
    """Count the sentences in a summary.

    Args:
        text: The summary.

    Returns:
        How many sentences it appears to hold.
    """
    return len([part for part in _SENTENCE_BREAK.split(text.strip()) if part])


class DocumentSummary(BaseModel):
    """What a document was about, in a few sentences."""

    summary: str = Field(
        description=(
            f"What the meeting was about and what it settled, in "
            f"{MIN_SUMMARY_SENTENCES} to {MAX_SUMMARY_SENTENCES} sentences."
        )
    )

    @field_validator("summary")
    @classmethod
    def _check_summary(cls, value: str) -> str:
        """Reject a summary that is empty or the wrong length."""
        summary = normalize(value)
        if not summary:
            raise ValueError("summary must not be empty")
        sentences = count_sentences(summary)
        if not MIN_SUMMARY_SENTENCES <= sentences <= MAX_SUMMARY_SENTENCES:
            raise ValueError(
                f"summary must run to {MIN_SUMMARY_SENTENCES}-"
                f"{MAX_SUMMARY_SENTENCES} sentences, not {sentences}"
            )
        return summary


class TopicAssignment(BaseModel):
    """The categories one document belongs under."""

    topics: list[str] = Field(
        description=(
            f"Up to {MAX_TOPICS} category names for this meeting, preferring "
            f"the existing categories."
        )
    )

    @field_validator("topics")
    @classmethod
    def _check_topics(cls, value: list[str]) -> list[str]:
        """Reject too many topics, a blank one, or the same one twice."""
        topics = [_require_topic_name(name) for name in value]
        if len(topics) > MAX_TOPICS:
            raise ValueError(f"a document carries at most {MAX_TOPICS} topics")
        _reject_repeats(topics, "topic")
        return topics


class PriorityAssessment(BaseModel):
    """How soon a document's subject matter matters, and how much."""

    time_sensitivity: TimeSensitivity = Field(
        description=(
            "How soon this needs attention: urgent (days), near_term (weeks), "
            "long_term (a quarter or more), or none (no deadline at all)."
        )
    )
    business_impact: BusinessImpact = Field(
        description=(
            "How much of the business this moves: critical, significant, "
            "moderate, or minor."
        )
    )


class TopicMerge(BaseModel):
    """One group of category names that mean the same thing."""

    keep: str = Field(description="The category name that survives the merge.")
    merge: list[str] = Field(
        description="Existing category names that mean the same as `keep`."
    )

    @field_validator("keep")
    @classmethod
    def _check_keep(cls, value: str) -> str:
        """Reject a merge with nothing to merge into."""
        return _require_topic_name(value)

    @field_validator("merge")
    @classmethod
    def _check_merge(cls, value: list[str]) -> list[str]:
        """Reject an empty merge list, a blank name, or a repeated one."""
        names = [_require_topic_name(name) for name in value]
        if not names:
            raise ValueError("a merge has to name at least one category to fold in")
        _reject_repeats(names, "category")
        return names


class TopicMerges(BaseModel):
    """Every merge the dedupe pass proposes.

    Structured output needs an object at the top level, so the groups are
    wrapped rather than returned bare.
    """

    merges: list[TopicMerge] = Field(
        description="One group per set of duplicate categories. May be empty."
    )


def _require_topic_name(value: str) -> str:
    """Return a category name normalized onto one line, if it is usable.

    Args:
        value: The candidate name.

    Returns:
        The normalized name.

    Raises:
        ValueError: If the name is empty or too long to be a category.
    """
    name = normalize(value)
    if not name:
        raise ValueError("a category name must not be empty")
    if len(name) > MAX_TOPIC_CHARS:
        raise ValueError(
            f"a category name must be at most {MAX_TOPIC_CHARS} characters, "
            f"not {len(name)}"
        )
    return name


def _reject_repeats(names: list[str], what: str) -> None:
    """Reject a list that names the same thing twice.

    Case is ignored, because "Supply chain" and "Supply Chain" are one
    category being listed twice rather than two categories.

    Args:
        names: The normalized names.
        what: What is being listed, for the error message.

    Raises:
        ValueError: If any name appears more than once.
    """
    seen = {name.casefold() for name in names}
    if len(seen) != len(names):
        raise ValueError(f"the same {what} is listed more than once")
