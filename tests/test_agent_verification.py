"""Tests for reading the verification model's reply.

What the graph does with a rejection, and with a reply it cannot read, is
tested in ``tests/test_agent_answer.py``, against the real endpoint. What is
under test here is the part that has no model in it: reading the sentinel
and the labelled lines the verification prompt asks for, and telling a
readable reply apart from one that is not.

Nothing here loads a model or reaches Ollama.
"""

from __future__ import annotations

from corpus_query.agent.verification import Verdict, read_verdict


def test_the_sentinel_means_nothing_was_rejected() -> None:
    """Every claim held up, so there is nothing to redraft."""
    assert read_verdict("VERIFIED") == Verdict(rejected=[], readable=True)


def test_the_sentinel_is_read_through_emphasis_and_punctuation() -> None:
    """A small model dressing up the sentinel still reads as the sentinel."""
    assert read_verdict("**VERIFIED.**") == Verdict(rejected=[], readable=True)


def test_one_unsupported_claim_is_read_from_its_label() -> None:
    """A single rejected claim comes back on its own, and the reply reads."""
    verdict = read_verdict("UNSUPPORTED: Marcus said the freeze moved to March 19th.")
    assert verdict == Verdict(
        rejected=["Marcus said the freeze moved to March 19th."], readable=True
    )


def test_several_unsupported_claims_are_each_read() -> None:
    """One rejected claim per labelled line, in the order they were written."""
    reply = (
        "UNSUPPORTED: The freeze moved to March 19th.\n"
        "UNSUPPORTED: Priya approved the change."
    )
    assert read_verdict(reply).rejected == [
        "The freeze moved to March 19th.",
        "Priya approved the change.",
    ]


def test_labelled_lines_among_echoed_prose_still_read() -> None:
    """A real rejection is read out even when the model pads it with noise.

    A small model does not always stop at the labelled line the prompt
    asks for; it sometimes echoes the drafted answer around it. Only the
    labelled line counts as a rejection, and the reply is still readable
    because that line is there.
    """
    reply = (
        "The record indicates that Renata approved the goodwill offer, as "
        "the passage titled 'Contract and Liability Position' states:\n"
        "> Pending Renata's approval\n"
        "UNSUPPORTED: The record indicates that Renata approved the "
        "goodwill offer.\n"
        "The passage does not provide a separate date for the approval."
    )
    verdict = read_verdict(reply)
    assert verdict.readable is True
    assert verdict.rejected == [
        "The record indicates that Renata approved the goodwill offer."
    ]


def test_prose_with_no_labelled_line_is_unreadable() -> None:
    """The model echoing the draft back, with no label anywhere, is not a claim.

    Treating every such line as its own rejection was the bug: a redraft
    cannot fix noise that was never a real rejection, and a turn that keeps
    hitting this would burn every regeneration attempt on nothing. This is
    the case the fix reports instead of guessing at.
    """
    reply = (
        "The record mentions two specific support tickets related to the "
        "Drossick account:\n"
        "1. Ticket TKT-4138, opened 2026-04-08.\n"
        "2. Ticket TKT-4140, opened 2026-04-14.\n"
        "The record does not provide a total count or average resolution "
        "time."
    )
    verdict = read_verdict(reply)
    assert verdict.readable is False
    assert verdict.rejected == []


def test_an_empty_reply_is_read_as_verified() -> None:
    """A blank reply is taken as nothing to redraft over, not a rejection."""
    assert read_verdict("   ") == Verdict(rejected=[], readable=True)
