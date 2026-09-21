"""Reading the verification model's judgement of a drafted answer.

The model is shown the passages a search returned and the answer drafted
from them, and asked whether every claim in the answer is something one of
those passages actually says. This module reads the reply: the sentinel that
means every claim held up, or the claims that did not — the same shape
:mod:`corpus_query.agent.routing` reads the routing model's reply in, for the
same reason: a small model asked for a word or a short list reliably writes
one of those two things, and reading it is simpler than parsing structured
output it was never asked to produce.

Reliably, but not always. A model that does not follow the
``UNSUPPORTED: <claim>`` shape sometimes echoes the drafted answer back
across several unlabelled lines instead. Reading each of those lines as its
own rejected claim — which an earlier version of this module did — turns
that noise into claims nothing actually rejected, and a redraft cannot fix a
claim that was never really there: it burns every attempt in
:data:`corpus_query.agent.graph.MAX_REGENERATIONS` without the answer
changing in any way that would satisfy a check that misread its own input.
So only labelled lines count as rejections here, and a reply that is neither
the sentinel nor carries a single labelled line is reported as unreadable
rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: What the verification model says when every claim in the answer is
#: supported by a passage it was shown.
VERIFIED = "VERIFIED"

#: The label a rejected claim's line opens with.
UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class Verdict:
    """What the verification model's reply said, read plainly."""

    rejected: list[str] = field(default_factory=list)
    """The claims read off ``UNSUPPORTED:`` lines. Empty when the answer was
    verified, and necessarily empty when the reply was not readable, since
    nothing was actually parsed out of it in that case."""

    readable: bool = True
    """Whether the reply was something this module could act on: the
    sentinel, or at least one labelled line. False for a reply that was
    neither — prose that did not follow the shape it was asked for, which is
    not evidence of anything rejected and is not evidence of nothing
    rejected either."""


def read_verdict(reply: str) -> Verdict:
    """Read the verification model's reply.

    Args:
        reply: What the model said when it was shown the passages and the
            drafted answer.

    Returns:
        The verdict: the claims flagged as unsupported, and whether the
        reply was readable at all. An empty reply is read the same as the
        sentinel, since a redraft chasing nothing is worse than no redraft.
        A labelled line is read wherever it falls, so a reply mixing real
        rejections with echoed prose still yields the rejections and none
        of the noise around them.
    """
    text = reply.strip()
    if not text:
        return Verdict()
    if _sentinel(text.splitlines()[0]):
        return Verdict()
    labelled = [
        claim
        for claim in (_labelled(line) for line in text.splitlines())
        if claim is not None
    ]
    return Verdict(rejected=labelled, readable=bool(labelled))


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


def _labelled(line: str) -> str | None:
    """Read one line as a rejected claim, if it is labelled as one.

    Args:
        line: One line of the reply.

    Returns:
        The claim, with the ``UNSUPPORTED:`` label and surrounding emphasis
        stripped off — or ``None`` for a line that is not labelled, which
        includes a blank line and prose the model wrote without the label
        it was asked for.
    """
    stripped = line.strip()
    if not stripped:
        return None
    label, separator, rest = stripped.partition(":")
    if separator and label.strip().strip("*_ ").upper() == UNSUPPORTED:
        claim = rest.strip()
        return claim or None
    return None
