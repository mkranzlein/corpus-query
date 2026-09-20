"""Tests for reading a transcript and cutting it into windows of turns."""

from __future__ import annotations

from corpus_query.ingest.chunk import TARGET_WORDS, Chunk, count_words
from corpus_query.ingest.transcripts import chunk_turns
from corpus_query.transcripts.parse import ParsedTurn, parse_transcript
from corpus_query.transcripts.render import render_meeting, render_turn

SPEAKERS = ("Priya", "Marcus", "Sofia")


def make_turn(index: int, words: int) -> ParsedTurn:
    """Build one turn of a known length.

    Args:
        index: Which turn this is, used to pick a speaker and vary the text.
        words: How many words the spoken text holds.

    Returns:
        A turn whose rendered line is what a transcript would carry.
    """
    speaker = SPEAKERS[index % len(SPEAKERS)]
    text = " ".join(f"w{index}-{position}" for position in range(words))
    return ParsedTurn(speaker=speaker, text=text, line=render_turn(speaker, text))


def make_turns(*lengths: int) -> list[ParsedTurn]:
    """Build turns of the given spoken-word lengths, in order."""
    return [make_turn(index, words) for index, words in enumerate(lengths)]


def covered(chunks: list[Chunk]) -> set[int]:
    """Return every turn index that appears in some chunk."""
    return {
        index
        for chunk in chunks
        for index in range(chunk.span_start, chunk.span_end + 1)
    }


def test_every_turn_lands_in_at_least_one_chunk():
    turns = make_turns(*[40] * 20)
    chunks = chunk_turns(turns, target_words=100)
    assert covered(chunks) == set(range(len(turns)))


def test_ordinals_run_from_zero_without_gaps():
    chunks = chunk_turns(make_turns(*[40] * 20), target_words=100)
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_a_chunk_never_starts_or_ends_mid_turn():
    turns = make_turns(*[40] * 20)
    for chunk in chunk_turns(turns, target_words=100):
        span = turns[chunk.span_start : chunk.span_end + 1]
        assert chunk.text == "\n".join(turn.line for turn in span)


def test_a_window_accumulates_turns_until_it_passes_the_target():
    turns = make_turns(*[40] * 20)
    chunks = chunk_turns(turns, target_words=100)
    # The last window takes whatever is left, so it may fall short.
    for chunk in chunks[:-1]:
        assert chunk.word_count >= 100


def test_adjacent_windows_share_a_turn():
    chunks = chunk_turns(make_turns(*[40] * 20), target_words=100)
    assert len(chunks) > 1
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.span_start == earlier.span_end


def test_every_adjacent_pair_of_turns_is_whole_in_some_chunk():
    turns = make_turns(*[40] * 20)
    chunks = chunk_turns(turns, target_words=100)
    pairs = {
        (index, index + 1)
        for chunk in chunks
        for index in range(chunk.span_start, chunk.span_end)
    }
    assert pairs == {(index, index + 1) for index in range(len(turns) - 1)}


def test_a_turn_longer_than_the_target_becomes_its_own_chunk():
    turns = make_turns(30, 30, 400, 30, 30)
    chunks = chunk_turns(turns, target_words=100)
    alone = [chunk for chunk in chunks if chunk.span_start == chunk.span_end == 2]
    assert alone, [(chunk.span_start, chunk.span_end) for chunk in chunks]
    assert alone[0].text == turns[2].line


def test_a_single_oversized_turn_is_the_whole_document():
    turns = make_turns(400)
    chunks = chunk_turns(turns, target_words=100)
    assert len(chunks) == 1
    assert (chunks[0].span_start, chunks[0].span_end) == (0, 0)


def test_a_short_document_is_one_chunk():
    turns = make_turns(10, 10, 10)
    chunks = chunk_turns(turns, target_words=100)
    assert len(chunks) == 1
    assert (chunks[0].span_start, chunks[0].span_end) == (0, 2)


def test_no_turns_means_no_chunks():
    assert chunk_turns([]) == []


def test_word_count_matches_the_chunk_text():
    for chunk in chunk_turns(make_turns(*[40] * 20), target_words=100):
        assert chunk.word_count == count_words(chunk.text)


def test_chunking_the_same_document_twice_gives_the_same_chunks():
    turns = make_turns(*[40] * 20)
    assert chunk_turns(turns, target_words=100) == chunk_turns(turns, target_words=100)


def test_chunk_text_is_byte_identical_to_a_span_of_the_source(make_meeting):
    meeting = make_meeting(
        turns=[
            {"speaker": turn.speaker, "text": turn.text}
            for turn in make_turns(*[40] * 20)
        ]
    )
    rendered = render_meeting(meeting)
    chunks = chunk_turns(parse_transcript(rendered).turns, target_words=100)
    for chunk in chunks:
        assert chunk.text in rendered
        start = rendered.index(chunk.text)
        assert rendered[start : start + len(chunk.text)].encode() == chunk.text.encode()


def test_the_default_target_is_used_when_none_is_given():
    turns = make_turns(*[TARGET_WORDS // 2] * 6)
    chunks = chunk_turns(turns)
    assert len(chunks) > 1
    assert all(chunk.word_count >= TARGET_WORDS for chunk in chunks[:-1])
