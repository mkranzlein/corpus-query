"""Tests for assembling the generation prompt."""

from __future__ import annotations

import pytest

from corpus_query.transcripts.length import TRANSCRIPT_WORDS_PER_MINUTE
from corpus_query.transcripts.prompt import (
    PROMPT_FILE,
    PromptError,
    build_prompt,
    fill,
    load_template,
)
from corpus_query.transcripts.roster import first_names, read_roster
from corpus_query.transcripts.summaries import NO_PRIOR_MEETINGS, PriorMeeting


@pytest.fixture
def people(roster_path):
    """Return the committed roster."""
    return read_roster(roster_path)


def test_a_token_is_substituted():
    assert fill("Write {{batch}}.", {"batch": "5 meetings"}) == "Write 5 meetings."


def test_a_token_nothing_fills_in_is_an_error():
    with pytest.raises(PromptError, match="batch"):
        fill("Write {{batch}}.", {})


def test_a_value_the_prompt_never_uses_is_an_error():
    with pytest.raises(PromptError, match="flavor"):
        fill("Write meetings.", {"flavor": "brisk"})


def test_the_committed_prompt_is_fully_filled_in(people):
    prompt = build_prompt(count=5, words=1500, people=people)
    assert "{{" not in prompt
    assert PROMPT_FILE.is_file()


def test_the_prompt_carries_the_batch_size_and_word_target(people):
    prompt = build_prompt(count=3, words=1200, people=people)
    assert "Write 3 meetings" in prompt
    assert "1,200 transcript words" in prompt


def test_the_prompt_asks_for_a_spread_around_the_target(people):
    prompt = build_prompt(count=5, words=1500, people=people)
    assert "750" in prompt
    assert "2,250" in prompt


def test_the_prompt_states_the_words_to_minutes_rate(people):
    prompt = build_prompt(count=5, words=1500, people=people)
    assert f"{TRANSCRIPT_WORDS_PER_MINUTE} transcript words" in prompt
    assert "60-minute meeting" in prompt


def test_the_prompt_names_everyone_on_the_roster(people):
    prompt = build_prompt(count=5, words=1500, people=people)
    for name in first_names(people):
        assert name in prompt


def test_a_first_batch_is_told_no_meetings_exist_yet(people):
    assert NO_PRIOR_MEETINGS in build_prompt(count=5, words=1500, people=people)


def test_a_later_batch_carries_the_earlier_summaries(people):
    prior = (PriorMeeting("Rev B schedule", "2026-02-11", "Held the rev B date."),)
    prompt = build_prompt(count=5, words=1500, people=people, prior=prior)
    assert NO_PRIOR_MEETINGS not in prompt
    assert "Held the rev B date." in prompt


def test_the_prompt_asks_for_the_planted_imperfections(people):
    prompt = build_prompt(count=5, words=1500, people=people).lower()
    assert "contradictory" in prompt
    assert "never answered" in prompt
    assert "opposite" in prompt
    assert "ramble" in prompt


def test_the_prompt_confines_dates_to_the_first_half_of_2026(people):
    prompt = build_prompt(count=5, words=1500, people=people)
    assert "2026-01-05" in prompt
    assert "2026-06-30" in prompt


def test_the_template_is_loadable_on_its_own():
    assert "{{roster}}" in load_template()


def test_a_missing_template_is_reported(tmp_path):
    with pytest.raises(PromptError, match="Could not read the prompt"):
        load_template(tmp_path / "absent.md")


def test_a_batch_of_one_asks_for_a_meeting_rather_than_meetings(people):
    assert "Write 1 meeting." in build_prompt(count=1, words=1500, people=people)
