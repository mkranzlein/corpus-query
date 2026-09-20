"""Assembling the generation prompt.

The prompt itself lives in ``prompt.md`` beside this module, never inline in
code. It is the part most likely to be revised by hand, and a markdown file is
what someone revising it wants to open.

Filling it in is a plain token substitution rather than :meth:`str.format`,
because the prompt is prose that may grow braces of its own — a JSON example,
a set notation — and a formatter would choke on them. A ``{{token}}`` is
unambiguous and survives editing.
"""

from __future__ import annotations

import re
from pathlib import Path

from corpus_query.transcripts.length import (
    TRANSCRIPT_WORDS_PER_MINUTE,
    minutes_for_words,
)
from corpus_query.transcripts.roster import Person, describe_roster
from corpus_query.transcripts.summaries import PriorMeeting, describe_prior_meetings

#: The prompt template, beside this module rather than under ``data``: it is
#: part of the package, and is loaded through the package's own path.
PROMPT_FILE = Path(__file__).with_name("prompt.md")

#: How far meetings spread around the word target, as fractions of it. Half to
#: one-and-a-half keeps the batch varied while averaging near the target.
SPREAD = (0.5, 1.5)

_TOKEN = re.compile(r"\{\{(\w+)\}\}")


class PromptError(Exception):
    """The prompt template is missing, or does not match what fills it."""


def load_template(path: Path | str = PROMPT_FILE) -> str:
    """Read the prompt template.

    Args:
        path: Path to the template.

    Returns:
        The template text.

    Raises:
        PromptError: If the template cannot be read.
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptError(f"Could not read the prompt at {path}: {exc}") from exc


def fill(template: str, values: dict[str, str]) -> str:
    """Substitute every ``{{token}}`` in a template.

    Args:
        template: The template text.
        values: One entry per token in the template.

    Returns:
        The filled-in text.

    Raises:
        PromptError: If the template uses a token that ``values`` does not
            supply, or supplies a value the template never uses. Either one
            means the two have drifted apart, which is worth failing on
            rather than quietly sending a prompt with a hole in it.
    """
    used = set(_TOKEN.findall(template))
    supplied = set(values)
    if missing := used - supplied:
        raise PromptError(
            f"The prompt uses {', '.join(sorted(missing))}, which nothing fills in."
        )
    if unused := supplied - used:
        raise PromptError(f"Nothing in the prompt uses {', '.join(sorted(unused))}.")
    return _TOKEN.sub(lambda match: values[match.group(1)], template)


def build_prompt(
    count: int,
    words: int,
    people: tuple[Person, ...],
    prior: tuple[PriorMeeting, ...] = (),
    template: str | None = None,
) -> str:
    """Assemble the prompt for one batch.

    Args:
        count: How many meetings this run asks for.
        words: The per-meeting transcript word target.
        people: The roster the cast is drawn from.
        prior: Summaries of meetings earlier batches produced, so this batch
            is steered away from repeating them.
        template: The template text. Read from :data:`PROMPT_FILE` when not
            given.

    Returns:
        The prompt, ready to send.

    Raises:
        PromptError: If the template cannot be read, or does not match the
            values that fill it.
    """
    low, high = (round(words * fraction) for fraction in SPREAD)
    return fill(
        load_template() if template is None else template,
        {
            "batch": f"{count} meeting{'' if count == 1 else 's'}",
            "words": f"{words:,}",
            "min_words": f"{low:,}",
            "max_words": f"{high:,}",
            "minutes": str(minutes_for_words(words)),
            "min_minutes": str(minutes_for_words(low)),
            "words_per_minute": str(TRANSCRIPT_WORDS_PER_MINUTE),
            "roster": describe_roster(people),
            "prior": describe_prior_meetings(prior),
        },
    )
