"""Tests for reading the verification model's reply.

What the graph does with a rejection is tested in
``tests/test_agent_answer.py``, against the real endpoint. What is under
test here is the part that has no model in it: reading the sentinel and the
labelled lines the verification prompt asks for.

Nothing here loads a model or reaches Ollama.
"""

from __future__ import annotations

from corpus_query.agent.verification import unsupported_claims


def test_the_sentinel_means_nothing_was_rejected() -> None:
    """Every claim held up, so there is nothing to redraft."""
    assert unsupported_claims("VERIFIED") == []


def test_the_sentinel_is_read_through_emphasis_and_punctuation() -> None:
    """A small model dressing up the sentinel still reads as the sentinel."""
    assert unsupported_claims("**VERIFIED.**") == []


def test_one_unsupported_claim_is_read_from_its_label() -> None:
    """A single rejected claim comes back on its own."""
    assert unsupported_claims(
        "UNSUPPORTED: Marcus said the freeze moved to March 19th."
    ) == ["Marcus said the freeze moved to March 19th."]


def test_several_unsupported_claims_are_each_read() -> None:
    """One rejected claim per line, in the order they were written."""
    reply = (
        "UNSUPPORTED: The freeze moved to March 19th.\n"
        "UNSUPPORTED: Priya approved the change."
    )
    assert unsupported_claims(reply) == [
        "The freeze moved to March 19th.",
        "Priya approved the change.",
    ]


def test_a_reply_without_the_label_is_passed_through_as_written() -> None:
    """A claim that lost its label is still a claim worth checking again."""
    assert unsupported_claims("The freeze moved to March 19th.") == [
        "The freeze moved to March 19th."
    ]


def test_an_empty_reply_rejects_nothing() -> None:
    """A blank reply is taken as nothing to redraft over, not a rejection."""
    assert unsupported_claims("   ") == []
