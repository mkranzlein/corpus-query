"""Tests for reading the rewrite model's reply.

What the graph does with a resolved query is tested in
``tests/test_agent_answer.py``, against the real endpoint. What is under
test here is the part that has no model in it: how the reply is cleaned up
before it is used.

Nothing here loads a model or reaches Ollama.
"""

from __future__ import annotations

from corpus_query.agent.rewriting import resolved_query


def test_the_reply_is_used_as_the_resolved_query() -> None:
    """An ordinary rewrite is passed through, whitespace trimmed."""
    assert (
        resolved_query(
            "  What did the refinery review decide about the compressor?  ",
            fallback="What about the refinery one?",
        )
        == "What did the refinery review decide about the compressor?"
    )


def test_quotation_marks_a_small_model_adds_are_stripped() -> None:
    """A rewrite wrapped in quotes is read as the question, not the quoting."""
    assert (
        resolved_query('"What tolerance did we set?"', fallback="what tolerance?")
        == "What tolerance did we set?"
    )


def test_an_empty_reply_falls_back_to_the_question_as_asked() -> None:
    """A blank rewrite is worth falling back on rather than searching nothing."""
    assert resolved_query("   ", fallback="Where are the boards?") == (
        "Where are the boards?"
    )
