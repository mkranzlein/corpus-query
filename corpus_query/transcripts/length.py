"""Measuring how much a meeting actually says.

A generated transcript is a *cleaned-up* transcript: what a transcriber app
emits once filler, false starts, and the rest of the noise of real speech are
dropped. Its size is measured in transcript words — the words people say — and
nothing else. Header fields, speaker markers, section headings, decisions, and
action items are excluded, because spoken text is what later gets chunked and
retrieved, so it is the number worth asking for and worth checking.

The word count is also what makes the corpus affordable. Speech runs at
roughly 125 words a minute, so a verbatim hour-long meeting is about 7,500
words, and twenty of them would be on the order of 200,000 output tokens. A
cleaned-up transcript of a few hundred to a couple of thousand words carries
the same substance at a fraction of that, which is why the generator asks for
a word target rather than a duration.

Nothing here converts words into minutes. A transcript states what was said;
how long the meeting ran is not recoverable from it, and a header that claimed
otherwise would be inventing a number.
"""

from __future__ import annotations

from corpus_query.transcripts.schema import Meeting


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
