"""Tests for the committed prompt files and the passes that fill them.

The prompts are files rather than strings in code, so these check that the
files exist, that every token in them is filled, and that the parts generated
from code — the vocabularies, the topic cap — reach the prompt rather than
being described in prose that could drift from them.
"""

from __future__ import annotations

import pytest

from corpus_query.enrich import passes, prompts
from corpus_query.enrich.documents import StoredDocument
from corpus_query.enrich.prompts import PromptError
from corpus_query.enrich.schema import (
    BUSINESS_IMPACT_VALUES,
    MAX_SUMMARY_SENTENCES,
    MAX_TOPICS,
    MIN_SUMMARY_SENTENCES,
    TIME_SENSITIVITY_VALUES,
)
from corpus_query.enrich.topics import NO_CATEGORIES

PROMPT_NAMES = ["summary", "topics", "priority", "dedupe"]


@pytest.fixture
def document() -> StoredDocument:
    """Return a document to assemble prompts around."""
    return StoredDocument(
        id=1,
        slug="rev-b-schedule",
        subject="Rev B schedule",
        meeting_date="2026-03-04",
        attendees=("Priya", "Marcus"),
        text="[Priya]: Where are we on the rev B boards?",
    )


@pytest.mark.parametrize("name", PROMPT_NAMES)
def test_every_prompt_is_a_committed_file(name):
    assert prompts.load(name).strip()


def test_a_missing_prompt_is_an_error_rather_than_an_empty_one():
    with pytest.raises(PromptError, match="Could not read the prompt"):
        prompts.load("no-such-pass")


@pytest.mark.parametrize(
    "build",
    [
        lambda document: passes.summary_prompt(document),
        lambda document: passes.topics_prompt(document, ["Firmware"]),
        lambda document: passes.priority_prompt(document),
    ],
)
def test_a_document_prompt_carries_the_document(build, document):
    prompt = build(document)

    assert document.subject in prompt
    assert document.meeting_date in prompt
    assert document.text in prompt
    assert "Priya, Marcus" in prompt
    assert "{{" not in prompt


def test_the_summary_prompt_states_the_length_validation_will_enforce():
    prompt = passes.summary_prompt(
        StoredDocument(
            id=1,
            slug="s",
            subject="s",
            meeting_date="2026-01-05",
            attendees=(),
            text="t",
        )
    )

    assert str(MIN_SUMMARY_SENTENCES) in prompt
    assert str(MAX_SUMMARY_SENTENCES) in prompt


def test_the_topic_prompt_carries_the_categories_that_exist_now(document):
    prompt = passes.topics_prompt(document, ["Firmware", "Supply Chain"])

    assert "- Firmware" in prompt
    assert "- Supply Chain" in prompt
    assert str(MAX_TOPICS) in prompt


def test_the_topic_prompt_says_so_when_there_are_no_categories_yet(document):
    assert NO_CATEGORIES in passes.topics_prompt(document, [])


def test_the_priority_prompt_lists_both_vocabularies(document):
    prompt = passes.priority_prompt(document)

    for value in TIME_SENSITIVITY_VALUES + BUSINESS_IMPACT_VALUES:
        assert f"`{value}`" in prompt


def test_the_dedupe_prompt_carries_the_whole_category_list():
    prompt = passes.dedupe_prompt(["Supply Chain", "Supply Chain Risk"])

    assert "- Supply Chain\n- Supply Chain Risk" in prompt
    assert "{{" not in prompt


def test_a_template_that_has_drifted_from_what_fills_it_is_an_error():
    with pytest.raises(PromptError, match="which nothing fills in"):
        prompts.fill("{{unfilled}}", {})
