"""Turning a turn into a question that stands on its own.

A follow-up like "what about the refinery one?" means something once you
have read the rest of the conversation and nothing once you have not, and
``search_corpus`` only ever sees the words the model puts in front of it.
This module reads the rewrite model's reply: the same question, with what it
points back at spelled out, so retrieval has something it can act on.

Nothing here decides whether a turn needs rewriting — the graph runs this
model call for every turn that has prior conversation, and a question that
already stood on its own comes back unchanged. That costs a model call
rather than a wrong guess about which turns need one.
"""

from __future__ import annotations

#: Quotation marks stripped off a rewrite. A small model asked for "the
#: question alone" sometimes wraps it in the kind it would use to quote
#: someone, straight or curly.
_QUOTES = "\"'“”‘’"


def resolved_query(reply: str, fallback: str) -> str:
    """Read the rewrite model's reply.

    Args:
        reply: What the model wrote back.
        fallback: The question as the user actually typed it, used when the
            model's reply is empty. A blank rewrite is worth falling back
            on rather than searching for nothing.

    Returns:
        The standalone question, with surrounding whitespace and quotation
        marks stripped off.
    """
    text = reply.strip().strip(_QUOTES).strip()
    return text if text else fallback.strip()
