"""Recognizing a correction typed in conversation, and recording it.

"No, that's wrong — the freeze moved to March 19th" is not a question. It
says an earlier answer was wrong and what is right instead, and searching
the corpus for it would spend a call to produce a worse turn. The model is
offered a second tool, ``record_correction``, next to ``search_corpus``, and
the system prompt says what makes a turn a correction. Deciding whether a
turn is one is the model's call; everything after that is this module's.

The tool is never run the way ``search_corpus`` is. A call to it is routed
into a node of the graph's own, which settles which earlier answer is being
corrected, writes the correction through the same store ``POST
/corrections`` writes to, and says what it recorded in words this module
chooses rather than the model. That last part is deliberate: the one thing
the user must be able to trust about a correction turn is whether the
correction landed, and a model paraphrasing a write it cannot see is not
something to trust about that.

Which answer is being corrected
===============================

Every answer an agent gives is keyed by the id of the question that asked
for it: the agent mints the answer's id before it answers and gives it to
the question's message, and the API writes the answer row under that same
id. So the conversation alone says which row each earlier answer is, with no
lookup by thread or by position in a table.

The model names the answer it means by its number in a list shown to it,
and the rules for a call that does not are fixed here rather than left to
the model:

- a number that is on the list is the answer it names
- no number, with only one earlier answer, is that answer — there is
  nothing else it could mean
- no number with more than one earlier answer, or a number that is not on
  the list, is asked about, and nothing is recorded until the user says

A turn that recorded a correction, or asked which answer one was meant for,
is not itself an answer, and is left off the list.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, ValidationError

from corpus_query.store.capture import UnknownAnswerError

#: What the tool is called in the model's tool schema.
TOOL_NAME = "record_correction"

#: Writes one correction and returns the stored row: the answer's id, what
#: was wrong, and what is right, in that order.
#: :func:`corpus_query.store.capture.record_correction` with its connection
#: bound is the one the service uses.
type Recorder = Callable[[str, str, str], dict[str, Any]]

#: How much of an earlier answer the model is shown beside its number. Enough
#: to tell two answers apart by what they said; the whole answer is in the
#: conversation above for anything more.
_ANSWER_PREVIEW = 200


class RecordCorrection(BaseModel):
    """The tool's arguments, as the model is shown them."""

    what_was_wrong: str = Field(
        description="What the earlier answer said that the user says is "
        "wrong, in a short sentence."
    )
    what_is_right: str = Field(
        description="What the user says is true instead, in their words as "
        "far as possible."
    )
    answer_number: int | None = Field(
        default=None,
        description="Which earlier answer this corrects, by its number in "
        "the list of earlier answers. Leave it out only when you cannot "
        "tell which one the user means.",
    )


def correction_tool() -> StructuredTool:
    """Build the tool the model is offered for recording a correction.

    Only its schema is ever used. The graph routes a call to it into a node
    of its own rather than running it — see the module docstring — so the
    function behind it refuses to run rather than pretending to record.

    Returns:
        The tool, ready to be bound to a model.
    """

    async def record_correction(
        what_was_wrong: str, what_is_right: str, answer_number: int | None = None
    ) -> str:
        """Refuse to run: the graph records corrections itself."""
        raise RuntimeError(
            "record_correction is handled by the agent's graph, not run as a tool"
        )

    return StructuredTool.from_function(
        coroutine=record_correction,
        name=TOOL_NAME,
        description=(
            "Record that the user has corrected one of your earlier answers "
            "in this conversation: what it said that was wrong, and what is "
            "right instead. Call it instead of searching, and only when the "
            "user states specifically what is right. Do not call it for a "
            "question, or for disagreement that does not say what is right."
        ),
        args_schema=RecordCorrection,
    )


@dataclass(frozen=True)
class EarlierAnswer:
    """One answer given earlier in the conversation, which may be corrected."""

    answer_id: str
    """The id the answer's row was written under."""

    question: str
    """What was asked."""

    answer: str
    """What was answered."""


@dataclass(frozen=True)
class Outcome:
    """What handling one call to the tool came to."""

    reply: str
    """What the agent says back to the user."""

    status: str
    """What the tool message records for the model, on later turns."""

    correction: dict[str, Any] | None = None
    """The correction as the store wrote it, or ``None`` when nothing was
    recorded."""


def correction_call(message: Any) -> dict[str, Any] | None:
    """Return the first call to the correction tool on a model reply.

    Args:
        message: The model's reply.

    Returns:
        The tool call, or ``None`` when the reply makes none.
    """
    for call in getattr(message, "tool_calls", None) or []:
        if call["name"] == TOOL_NAME:
            return call
    return None


def earlier_answers(messages: list[Any]) -> list[EarlierAnswer]:
    """List the answers given in a conversation, in the order given.

    Args:
        messages: The conversation before the current turn.

    Returns:
        One entry per turn that answered something, leaving out turns that
        recorded a correction or asked which answer one was meant for.
    """
    turns: list[list[Any]] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            turns.append([message])
        elif turns:
            turns[-1].append(message)
    answers = []
    for turn in turns:
        if any(correction_call(message) for message in turn):
            continue
        replies = [message for message in turn if isinstance(message, AIMessage)]
        if not replies or not turn[0].id:
            continue
        answers.append(
            EarlierAnswer(
                answer_id=turn[0].id,
                question=_text(turn[0]),
                answer=_text(replies[-1]),
            )
        )
    return answers


def numbered(answers: list[EarlierAnswer]) -> str:
    """Show the model the earlier answers it can name by number.

    Args:
        answers: The earlier answers, in order.

    Returns:
        A block to add to the system prompt.
    """
    lines = [
        f'{index}. Asked: "{answer.question}" Answered: "{_preview(answer.answer)}"'
        for index, answer in enumerate(answers, start=1)
    ]
    return (
        f"Earlier answers in this conversation, numbered for `{TOOL_NAME}`:\n"
        + "\n".join(lines)
    )


def handle(
    call: dict[str, Any],
    answers: list[EarlierAnswer],
    recorder: Recorder | None,
) -> Outcome:
    """Settle which answer a correction is for, and record it.

    Args:
        call: The model's call to the correction tool.
        answers: The earlier answers in this conversation, in order.
        recorder: What writes a correction, or ``None`` when this agent has
            nowhere to write one.

    Returns:
        What was recorded, if anything, and what to say about it.
    """
    if recorder is None:
        return _not_recorded(
            "Corrections are not being recorded here, so nothing was saved."
        )
    if not answers:
        return _not_recorded(
            "There is no earlier answer in this conversation to correct, so "
            "nothing was recorded."
        )
    try:
        args = RecordCorrection.model_validate(call.get("args") or {})
    except ValidationError:
        args = None
    wrong = args.what_was_wrong.strip() if args else ""
    right = args.what_is_right.strip() if args else ""
    if not wrong or not right:
        return _not_recorded(
            "I can record a correction once I know both what my answer got "
            "wrong and what is right instead. What should it have said? "
            "Nothing has been recorded yet."
        )
    target = _referent(args.answer_number, answers)
    if target is None:
        return _not_recorded(_which_answer(answers))
    try:
        written = recorder(target.answer_id, wrong, right)
    except UnknownAnswerError:
        return _not_recorded(
            f'I could not record that correction: my answer to "'
            f'{target.question}" is not in the record store, so there is '
            f"nothing to attach it to."
        )
    return Outcome(
        reply=(
            f'I\'ve recorded your correction to my answer to "{target.question}". '
            f"What was wrong: {_sentence(wrong)} What is right: {_sentence(right)} "
            f"It is kept for review, and does not change how later questions "
            f"are answered."
        ),
        status=(
            f"Recorded correction {written['id']} against answer {target.answer_id}."
        ),
        correction=written,
    )


def _referent(number: int | None, answers: list[EarlierAnswer]) -> EarlierAnswer | None:
    """Settle which earlier answer a correction names.

    Args:
        number: The number the model gave, or ``None``.
        answers: The earlier answers, in order. Not empty.

    Returns:
        The answer being corrected, or ``None`` when the call does not
        settle which one it is.
    """
    if number is None:
        return answers[0] if len(answers) == 1 else None
    if 1 <= number <= len(answers):
        return answers[number - 1]
    return None


def _which_answer(answers: list[EarlierAnswer]) -> str:
    """Ask which answer a correction is for.

    Args:
        answers: The earlier answers, in order.

    Returns:
        The question to put to the user, listing what they could mean.
    """
    listed = "\n".join(
        f'{index}. "{answer.question}"' for index, answer in enumerate(answers, 1)
    )
    return (
        "Which of my earlier answers are you correcting? Nothing is recorded "
        f"until I know. I answered:\n\n{listed}"
    )


def _not_recorded(reply: str) -> Outcome:
    """Build the outcome of a call that recorded nothing.

    Args:
        reply: What to say to the user.

    Returns:
        The outcome, with the same words recorded for the model.
    """
    return Outcome(reply=reply, status=f"Not recorded. {reply}")


def _sentence(text: str) -> str:
    """End a fragment with a full stop if it does not end with one already.

    Args:
        text: A short piece of text.

    Returns:
        The text, ending in sentence punctuation.
    """
    return text if text[-1] in ".!?" else f"{text}."


def _preview(text: str) -> str:
    """Shorten an answer to what fits beside its number.

    Args:
        text: The answer.

    Returns:
        The answer on one line, cut to :data:`_ANSWER_PREVIEW` characters.
    """
    flat = " ".join(text.split())
    if len(flat) <= _ANSWER_PREVIEW:
        return flat
    return flat[:_ANSWER_PREVIEW] + "…"


def _text(message: Any) -> str:
    """Return one message's text.

    Args:
        message: The message.

    Returns:
        Its text, as a string.
    """
    text = message.text
    return text if isinstance(text, str) else str(text)
