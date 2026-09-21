"""Reading the verification model's judgement of a drafted answer.

The model is shown the passages a search returned and the answer drafted
from them, and asked whether every claim in the answer is something one of
those passages actually says. This module reads the reply: the sentinel that
means every claim held up, or the claims that did not — the same shape
:mod:`corpus_query.agent.routing` reads the routing model's reply in, for the
same reason: a small model asked for a word or a short list reliably writes
one of those two things, and reading it is simpler than parsing structured
output it was never asked to produce.
"""

from __future__ import annotations

#: What the verification model says when every claim in the answer is
#: supported by a passage it was shown.
VERIFIED = "VERIFIED"


def unsupported_claims(reply: str) -> list[str]:
    """Read the verification model's reply.

    Args:
        reply: What the model said when it was shown the passages and the
            drafted answer.

    Returns:
        The claims it flagged as unsupported, one per labelled line — empty
        when the model judged the answer fully supported, which is also
        what an empty reply is taken to mean, since a redraft chasing
        nothing is worse than no redraft. A reply that arrives without the
        label is passed through as written: it is still a claim worth
        checking again.
    """
    text = reply.strip()
    if not text:
        return []
    if _sentinel(text.splitlines()[0]):
        return []
    claims = [_unlabelled(line) for line in text.splitlines() if line.strip()]
    return [claim for claim in claims if claim]


def _sentinel(line: str) -> bool:
    """Return whether a line is the model saying every claim held up.

    Args:
        line: The reply's first line.

    Returns:
        Whether it is the sentinel, read through the emphasis and
        punctuation a small model puts around a word it was told to say on
        its own.
    """
    return line.strip().strip("*_#`.:!").upper() == VERIFIED


def _unlabelled(line: str) -> str:
    """Strip the ``UNSUPPORTED:`` label off one line.

    Args:
        line: One line of the reply.

    Returns:
        The line's prose, without the label the prompt asked for.
    """
    stripped = line.strip()
    label, separator, rest = stripped.partition(":")
    if separator and label.strip().strip("*_ ").upper() == "UNSUPPORTED":
        return rest.strip()
    return stripped
