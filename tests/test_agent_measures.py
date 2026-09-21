"""Tests for the per-query numbers an answer is recorded with.

Pure functions over text and numbers. Nothing here calls a model, which is
the point of how they are defined.
"""

from __future__ import annotations

import pytest

from corpus_query.agent.measures import (
    citation_coverage,
    content_words,
    sentences,
    strongest_search,
)
from corpus_query.agent.retrieval import found

PASSAGE = (
    "Hiring Plan (2026-05-19, Priya, Marcus, Sofia, Renata, turns 12-14)\n"
    "[Marcus]: Fully loaded with benefits and overhead, call it a hundred and "
    "sixty to a hundred and eighty thousand per head."
)

OTHER = (
    "Q1 Sales Pipeline Review (2026-03-02, Elena, Jamal, turns 3-5)\n"
    "[Elena]: The Brannock renewal is the largest deal in the pipeline."
)


def test_function_words_carry_no_claim() -> None:
    """What is left of a sentence is what it asserts."""
    assert content_words("The cost was set at a hundred and sixty.") == {
        "cost",
        "set",
        "hundred",
        "sixty",
    }


def test_sentences_end_at_terminal_punctuation() -> None:
    """A full stop inside a number does not end a sentence."""
    assert sentences("It costs 4.2 million. Priya approved it! Why?  ") == [
        "It costs 4.2 million.",
        "Priya approved it!",
        "Why?",
    ]


def test_an_answer_drawn_from_its_passage_is_fully_covered() -> None:
    """Every sentence the passage bears out counts."""
    answer = (
        "In the hiring plan meeting, Marcus put the fully loaded cost at a "
        "hundred and sixty to a hundred and eighty thousand per head."
    )

    assert citation_coverage(answer, [PASSAGE, OTHER]) == 1.0


def test_a_sentence_no_passage_bears_out_is_not_covered() -> None:
    """Coverage is the share of sentences, so one invented sentence of two
    halves it."""
    answer = (
        "Marcus put the fully loaded cost at a hundred and sixty to a hundred "
        "and eighty thousand per head. The board approved three new offices "
        "in Singapore last spring."
    )

    assert citation_coverage(answer, [PASSAGE, OTHER]) == 0.5


def test_support_has_to_come_from_one_passage() -> None:
    """Words scattered across two passages do not add up to support.

    Three of this sentence's seven content words are in the hiring passage
    and three others in the sales one. Neither alone holds half of them;
    the two together would.
    """
    answer = "Marcus overhead sixty Elena Brannock renewal Singapore."

    assert citation_coverage(answer, [PASSAGE, OTHER]) == 0.0
    assert citation_coverage(answer, [PASSAGE + "\n" + OTHER]) == 1.0


def test_exactly_half_the_words_is_enough() -> None:
    """The threshold is at least half, not more than half."""
    # Content words: marcus, overhead, singapore, spring.
    assert citation_coverage("Marcus overhead Singapore spring.", [PASSAGE]) == 1.0
    # Content words: marcus, singapore, spring.
    assert citation_coverage("Marcus Singapore spring.", [PASSAGE]) == 0.0


def test_the_source_line_counts_as_part_of_the_passage() -> None:
    """Naming the document and who was there is drawing on the passage."""
    assert citation_coverage("Renata attended the hiring plan.", [PASSAGE]) == 1.0


def test_nothing_retrieved_is_not_measured() -> None:
    """With no passage to check against, coverage is unknown, not zero."""
    assert citation_coverage("The record does not say.", []) is None


def test_an_answer_with_no_content_words_is_not_measured() -> None:
    """A sentence that asserts nothing is counted in neither direction."""
    assert citation_coverage("", [PASSAGE]) is None
    assert citation_coverage("It is what it is.", [PASSAGE]) is None


def test_the_strongest_search_supplies_both_numbers() -> None:
    """The margin comes from the same search as the top score."""
    assert strongest_search(
        [
            {"top_score": 2.0, "margin": 1.5},
            {"top_score": 6.0, "margin": 0.25},
            {"top_score": None, "margin": None},
        ]
    ) == (6.0, 0.25)


@pytest.mark.parametrize(
    "confidences", [[], [{"top_score": None, "margin": None}], [{}]]
)
def test_no_search_that_returned_anything_is_not_measured(confidences) -> None:
    """Nothing ranked, so there is no score to report."""
    assert strongest_search(confidences) == (None, None)


def test_a_search_with_one_result_has_a_score_and_no_margin() -> None:
    """A margin needs two results."""
    assert strongest_search([{"top_score": 3.0, "margin": None}]) == (3.0, None)


def test_a_search_artifact_is_read_back_whole() -> None:
    """What the tool wrote is what the graph reads."""
    artifact = {
        "citations": [{"chunk_id": 1}],
        "passages": [PASSAGE],
        "confidence": {"top_score": 4.5, "margin": 1.25},
    }

    assert found(artifact) == artifact


def test_a_search_checkpointed_before_it_carried_measurements_still_reads() -> None:
    """An older thread's tool message holds a bare list of citations."""
    assert found([{"chunk_id": 1}]) == {
        "citations": [{"chunk_id": 1}],
        "passages": [],
        "confidence": {},
    }
    assert found(None) == {"citations": [], "passages": [], "confidence": {}}
