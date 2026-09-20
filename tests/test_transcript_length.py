"""Tests for counting what a meeting actually says."""

from __future__ import annotations

from corpus_query.transcripts.length import transcript_words


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


def test_a_longer_transcript_counts_higher(make_meeting):
    short = make_meeting(turns=turns_of(750))
    long = make_meeting(turns=turns_of(2250))
    assert transcript_words(short) == 750
    assert transcript_words(long) == 2250
