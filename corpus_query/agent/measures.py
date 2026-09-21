"""The per-query numbers an answer carries, computed without a model.

Each answer is recorded with a handful of numbers that are cheap to read
across thousands of rows: how well retrieval matched, how much of the answer
the retrieved passages bear out, how long it took, and what answered. The
two computed here are the ones that need a definition.

Nothing here calls a model. A measurement that needed one would cost a model
call on every question to produce, and would drift whenever the model that
produced it changed — which is the thing these numbers are meant to notice.

Citation coverage
=================

The share of the answer's sentences that the passages the turn retrieved
bear out, from 0 to 1. Precisely:

1. The answer is split into sentences at ``.``, ``!``, or ``?`` followed by
   whitespace.
2. Each sentence is reduced to its content words: lowercased runs of letters
   and digits, with the common English function words in
   :data:`FUNCTION_WORDS` removed. A sentence left with none is not counted
   at all, in either direction.
3. A sentence is *supported* when at least half of its distinct content
   words appear in a single retrieved passage — the passage's source line
   (title, date, author or attendees, location) and its text, reduced the
   same way. One passage, not the union of all of them, so a sentence
   cannot be assembled from words scattered across unrelated passages.
4. Coverage is supported sentences over counted sentences.

It is ``None`` when the turn retrieved no passage, since there is nothing to
check against, and when the answer has no sentence with a content word in it.

It is a lexical measure, and it says so: a sentence that paraphrases a
passage in other words counts as unsupported, and a sentence that reuses a
passage's words to say something the passage does not counts as supported.
What it is for is noticing a shift across many answers — a model that has
started writing past its sources, or retrieval that has stopped returning
what the answers are built from — not grading one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

#: A sentence ends at one of these followed by whitespace.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

#: What a word is: a run of letters and digits, after lowercasing.
_WORD = re.compile(r"[a-z0-9]+")

#: The share of a sentence's content words one passage has to contain for
#: the sentence to count as supported.
SUPPORT_THRESHOLD = 0.5

#: Words that carry no claim of their own. Removed before a sentence is
#: compared with a passage, so that "the", "was", and "of" appearing in
#: every passage ever written do not count as support. Short on purpose: a
#: word left in here that should not be only makes coverage a little
#: easier to earn, the same way for every answer.
FUNCTION_WORDS = frozenset(
    """
    a about above after again against all also am an and any are as at be
    because been before being below between both but by can could did do does
    doing don down during each few for from further had has have having he
    her here hers herself him himself his how i if in into is it its itself
    just let me more most my myself no nor not now of off on once only or
    other our ours ourselves out over own s same say says said she should so
    some such t than that the their theirs them themselves then there these
    they this those through to too under until up very was we were what when
    where which while who whom why will with would you your yours yourself
    yourselves
    """.split()
)


def content_words(text: str) -> set[str]:
    """Reduce text to the words in it that can carry a claim.

    Args:
        text: Any text.

    Returns:
        Its distinct lowercased words, without :data:`FUNCTION_WORDS`.
    """
    return {word for word in _WORD.findall(text.lower()) if word not in FUNCTION_WORDS}


def sentences(text: str) -> list[str]:
    """Split text into sentences.

    Args:
        text: Prose.

    Returns:
        Its sentences, stripped, without empty ones.
    """
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def citation_coverage(answer: str, passages: Iterable[str]) -> float | None:
    """Measure how much of an answer the retrieved passages bear out.

    See the module docstring for the definition.

    Args:
        answer: The answer as it was given.
        passages: Every passage the turn retrieved, each as the model was
            shown it.

    Returns:
        The share of the answer's counted sentences that one passage
        supports, from 0 to 1, or ``None`` when there were no passages or
        no sentence was counted.
    """
    vocabularies = [content_words(passage) for passage in passages]
    if not vocabularies:
        return None
    counted = 0
    supported = 0
    for sentence in sentences(answer):
        words = content_words(sentence)
        if not words:
            continue
        counted += 1
        if any(
            len(words & vocabulary) >= SUPPORT_THRESHOLD * len(words)
            for vocabulary in vocabularies
        ):
            supported += 1
    if not counted:
        return None
    return supported / counted


def strongest_search(
    confidences: Iterable[Mapping[str, Any]],
) -> tuple[float | None, float | None]:
    """Pick the retrieval confidence a turn is recorded with.

    A turn can search more than once, and each search reports its own top
    score and margin. The turn is recorded with the search whose top result
    scored highest, and that same search's margin, so the two numbers always
    describe one ranking rather than a top score from one search beside a
    margin from another.

    Args:
        confidences: Each search's confidence signals, as ``/search``
            reports them.

    Returns:
        The top score and margin, or ``None`` for either one the chosen
        search did not report. Both are ``None`` when nothing was searched
        or no search came back with anything.
    """
    scored = [row for row in confidences if row.get("top_score") is not None]
    if not scored:
        return None, None
    best = max(scored, key=lambda row: row["top_score"])
    return best["top_score"], best.get("margin")
