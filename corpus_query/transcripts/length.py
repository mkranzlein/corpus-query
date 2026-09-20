"""Measuring how much a meeting actually says.

A generated transcript is a *cleaned-up* transcript: what a transcriber app
emits once filler, false starts, and the rest of the noise of real speech are
dropped. Its size is measured in transcript words — the words people say — and
nothing else. Header fields, speaker markers, section headings, decisions, and
action items are excluded, because spoken text is what later gets chunked and
retrieved, so it is the number worth asking for and worth checking.

The stated length in the header has to agree with that count. Verbatim speech
runs at about :data:`VERBATIM_WORDS_PER_MINUTE`, which is why a real hour-long
meeting transcribes to roughly 7,500 words; cleanup keeps around a fifth of
that, so a cleaned-up transcript carries about
:data:`TRANSCRIPT_WORDS_PER_MINUTE` words per minute of meeting. That ratio is
what turns a word target into a plausible duration, and what stops a header
claiming an hour for two hundred words.
"""

from __future__ import annotations

from corpus_query.transcripts.schema import Meeting

#: Roughly how fast people speak, in words a minute. Not used to convert
#: anything — it is here to explain the number below, and because it is the
#: figure that makes a verbatim corpus unaffordable.
VERBATIM_WORDS_PER_MINUTE = 125

#: Cleaned-up transcript words per minute of meeting. A 1,500-word transcript
#: is an hour-long meeting, a 750-word one half an hour.
TRANSCRIPT_WORDS_PER_MINUTE = 25

#: How far the stated length may drift from the word count before the two are
#: treated as disagreeing, as a fraction of the implied length. Generous on
#: purpose: rounding to a meeting-shaped number of minutes is normal, claiming
#: an hour for a five-minute conversation is not.
LENGTH_TOLERANCE = 0.4


def transcript_words(meeting: Meeting) -> int:
    """Count the words spoken in a meeting.

    Args:
        meeting: A validated meeting.

    Returns:
        The number of whitespace-separated words across every turn's text.
        Speaker names are not counted, since they are markers rather than
        speech.
    """
    return sum(len(turn.text.split()) for turn in meeting.turns)


def minutes_for_words(words: int) -> int:
    """Return the meeting length a word count implies.

    Args:
        words: A transcript word count.

    Returns:
        The length in whole minutes, at :data:`TRANSCRIPT_WORDS_PER_MINUTE`,
        never less than one.
    """
    return max(1, round(words / TRANSCRIPT_WORDS_PER_MINUTE))


def length_disagreement(
    meeting: Meeting, tolerance: float = LENGTH_TOLERANCE
) -> str | None:
    """Report a stated length that does not match what was said.

    Args:
        meeting: A validated meeting.
        tolerance: Allowed drift, as a fraction of the implied length.

    Returns:
        A sentence naming both numbers, or ``None`` when they agree.
    """
    words = transcript_words(meeting)
    implied = minutes_for_words(words)
    if abs(meeting.length_minutes - implied) <= tolerance * implied:
        return None
    return (
        f"length_minutes says {meeting.length_minutes} but the transcript is "
        f"{words} words, which is about {implied} minutes at "
        f"{TRANSCRIPT_WORDS_PER_MINUTE} transcript words a minute"
    )
