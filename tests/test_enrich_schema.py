"""Tests for what enrichment will and will not accept from a model.

Nothing here calls anything. These are the validators that stand between a
response and the store.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from corpus_query.enrich.schema import (
    BUSINESS_IMPACT_VALUES,
    MAX_TOPICS,
    TIME_SENSITIVITY_VALUES,
    DocumentSummary,
    PriorityAssessment,
    TopicAssignment,
    TopicMerge,
    TopicMerges,
    count_sentences,
)


def test_priority_is_two_fields_not_one_blended_score():
    assessment = PriorityAssessment(time_sensitivity="urgent", business_impact="minor")

    assert assessment.time_sensitivity == "urgent"
    assert assessment.business_impact == "minor"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("time_sensitivity", "pretty urgent"),
        ("time_sensitivity", "High"),
        ("business_impact", "enormous"),
        ("business_impact", ""),
    ],
)
def test_a_priority_outside_the_vocabulary_fails_validation(field, value):
    fields = {"time_sensitivity": "urgent", "business_impact": "minor"} | {field: value}

    with pytest.raises(ValidationError):
        PriorityAssessment(**fields)


def test_the_vocabularies_are_small_and_fixed():
    assert TIME_SENSITIVITY_VALUES == ("urgent", "near_term", "long_term", "none")
    assert BUSINESS_IMPACT_VALUES == (
        "critical",
        "significant",
        "moderate",
        "minor",
    )


@pytest.mark.parametrize("sentences", [2, 3, 5])
def test_a_summary_of_the_right_length_validates(sentences):
    text = " ".join(f"Sentence number {index}." for index in range(sentences))

    assert count_sentences(DocumentSummary(summary=text).summary) == sentences


@pytest.mark.parametrize(
    "text",
    [
        "One sentence only.",
        "One. Two. Three. Four. Five. Six.",
        "   ",
    ],
)
def test_a_summary_of_the_wrong_length_fails_validation(text):
    with pytest.raises(ValidationError):
        DocumentSummary(summary=text)


def test_a_summary_spanning_lines_is_collapsed():
    summary = DocumentSummary(summary="First part.\n\nSecond   part.").summary

    assert summary == "First part. Second part."


def test_up_to_five_topics_validate():
    topics = [f"Topic {index}" for index in range(MAX_TOPICS)]

    assert TopicAssignment(topics=topics).topics == topics


def test_a_sixth_topic_fails_validation():
    with pytest.raises(ValidationError):
        TopicAssignment(topics=[f"Topic {index}" for index in range(MAX_TOPICS + 1)])


def test_no_topics_at_all_is_allowed():
    assert TopicAssignment(topics=[]).topics == []


@pytest.mark.parametrize(
    "topics",
    [
        ["Supply Chain", "supply chain"],
        ["Firmware", ""],
        ["x" * 61],
    ],
)
def test_a_bad_topic_list_fails_validation(topics):
    with pytest.raises(ValidationError):
        TopicAssignment(topics=topics)


def test_a_merge_names_what_survives_and_what_is_folded_in():
    merge = TopicMerge(keep="Supply Chain", merge=["Supply Chain Risk"])

    assert merge.keep == "Supply Chain"
    assert merge.merge == ["Supply Chain Risk"]


@pytest.mark.parametrize(
    "merge",
    [
        {"keep": "Supply Chain", "merge": []},
        {"keep": "", "merge": ["Supply Chain Risk"]},
        {"keep": "Supply Chain", "merge": ["Risk", "risk"]},
    ],
)
def test_a_bad_merge_fails_validation(merge):
    with pytest.raises(ValidationError):
        TopicMerge(**merge)


def test_proposing_no_merges_at_all_is_a_valid_answer():
    assert TopicMerges(merges=[]).merges == []
