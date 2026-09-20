"""Tests for the transcript word count and the length it implies."""

from __future__ import annotations

import pytest

from corpus_query.transcripts.length import (
    length_disagreement,
    minutes_for_words,
    transcript_words,
)


def turns_of(words: int, speaker: str = "Priya") -> list[dict[str, str]]:
    """Build turns holding exactly ``words`` words.

    Args:
        words: How many words to say in total.
        speaker: Who says them.

    Returns:
        Turn dictionaries suitable for the meeting factory.
    """
    return [{"speaker": speaker, "text": " ".join(["word"] * words)}]


def test_counting_sums_the_words_across_turns(make_meeting):
    meeting = make_meeting(
        turns=[
            {"speaker": "Priya", "text": "one two three"},
            {"speaker": "Marcus", "text": "four five"},
        ]
    )
    assert transcript_words(meeting) == 5


def test_counting_ignores_speaker_names(make_meeting):
    named = make_meeting(turns=[{"speaker": "Marcus", "text": "one two"}])
    other = make_meeting(turns=[{"speaker": "Priya", "text": "one two"}])
    assert transcript_words(named) == transcript_words(other) == 2


def test_counting_ignores_decisions_and_action_items(make_meeting):
    bare = make_meeting(turns=turns_of(10), decisions=[], action_items=[])
    furnished = make_meeting(
        turns=turns_of(10),
        decisions=["A decision made up of a good number of words."],
        action_items=[{"assignee": "Priya", "task": "Do a thing with several words."}],
    )
    assert transcript_words(bare) == transcript_words(furnished) == 10


def test_runs_of_whitespace_do_not_inflate_the_count(make_meeting):
    meeting = make_meeting(turns=[{"speaker": "Priya", "text": "one   two\t three"}])
    assert transcript_words(meeting) == 3


@pytest.mark.parametrize(
    ("words", "minutes"),
    [(1500, 60), (750, 30), (2250, 90), (5, 1)],
)
def test_a_word_count_implies_a_plausible_length(words: int, minutes: int):
    assert minutes_for_words(words) == minutes


@pytest.mark.parametrize(
    ("length_minutes", "words"), [(60, 1500), (30, 750), (90, 2250)]
)
def test_the_stated_length_and_the_word_count_agree(
    make_meeting, length_minutes: int, words: int
):
    meeting = make_meeting(length_minutes=length_minutes, turns=turns_of(words))
    assert length_disagreement(meeting) is None


def test_a_header_cannot_claim_an_hour_for_two_hundred_words(make_meeting):
    meeting = make_meeting(length_minutes=60, turns=turns_of(200))
    complaint = length_disagreement(meeting)
    assert complaint is not None
    assert "200 words" in complaint
    assert "60" in complaint


def test_rounding_to_a_meeting_shaped_length_is_within_tolerance(make_meeting):
    # 1,340 words implies 54 minutes; calling that an hour is not a lie.
    meeting = make_meeting(length_minutes=60, turns=turns_of(1340))
    assert length_disagreement(meeting) is None


def test_a_long_meeting_that_says_nothing_much_is_caught(make_meeting):
    meeting = make_meeting(length_minutes=90, turns=turns_of(800))
    assert length_disagreement(meeting) is not None
