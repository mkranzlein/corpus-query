"""Tests for capturing a correction the user types in conversation.

Whether a turn is a correction is the model's judgement, and a scripted model
cannot test a judgement. What these can test is everything either side of
it: that the correction tool is offered only when there is something to
correct, that a call to it is recorded against the right answer through the
same store ``POST /corrections`` writes to, that nothing is searched on the
way, that the reply says what was recorded, and that a call which does not
settle which answer it is for, or what is right, records nothing and asks.

They drive the real application and the real graph, as the answer tests do,
with the scripted model and stubbed ranking from there. Nothing here loads a
model, reaches Ollama, or calls anything hosted.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from corpus_query.agent import corrections
from corpus_query.agent.prompts import load
from corpus_query.agent.retrieval import TOOL_NAME
from corpus_query.api.models import AnswerResponse
from corpus_query.store.capture import UnknownAnswerError
from test_agent_answer import (
    ScriptedModel,
    answered,
    answering_app,
    conversation,
    found,
    recorded,
    says,
    searches,
    verified,
)
from test_answer_stream import STREAM, events, names
from test_api import StubSearch

FREEZE = "When is the firmware freeze?"
BOARDS = "Where are the rev B boards?"
CORRECTION = "No, that's wrong. The freeze moved to March 19th."


def corrects(
    wrong: str = "It said the freeze is March 12th.",
    right: str = "The freeze moved to March 19th.",
    number: int | None = None,
    call_id: str = "fix-1",
) -> AIMessage:
    """Build a model reply that records a correction.

    Args:
        wrong: What the earlier answer got wrong.
        right: What is right instead.
        number: Which earlier answer it corrects, or None to leave it out.
        call_id: The tool call's id.

    Returns:
        The reply, with one call to the correction tool on it.
    """
    args: dict[str, Any] = {"what_was_wrong": wrong, "what_is_right": right}
    if number is not None:
        args["answer_number"] = number
    return AIMessage(
        "",
        tool_calls=[{"name": corrections.TOOL_NAME, "args": args, "id": call_id}],
    )


def answers_freeze(call_id: str = "call-1") -> list[AIMessage]:
    """Script the first answer: a search, a draft, and both checks."""
    return [
        searches("firmware freeze date", call_id=call_id),
        says("The firmware freeze is March 12th."),
        verified(),
        answered(),
    ]


def answers_boards(call_id: str = "call-2") -> list[AIMessage]:
    """Script a second, unrelated answer on the same thread."""
    return [
        says(BOARDS),
        searches("rev B boards", call_id=call_id),
        says("The rev B boards are two weeks out."),
        verified(),
        answered(),
    ]


def test_a_correcting_turn_is_recorded_against_the_answer_it_corrects() -> None:
    """The correction lands on the earlier answer's row, and nothing is searched."""
    model = ScriptedModel(
        [
            *answers_freeze(),
            # The rewrite model hands the correction back unchanged.
            says(CORRECTION),
            corrects(number=1),
        ]
    )
    search = StubSearch(result=found())
    app = answering_app(model, search)

    first, second = conversation(
        app,
        {"question": FREEZE},
        {"question": CORRECTION, "_thread_from": 0},
    )

    # Recorded against the answer it corrects, through the same store the
    # endpoint writes to, and returned on the response that recorded it.
    [written] = recorded()["corrections"]
    assert written["answer_id"] == first["answer_id"]
    assert written["question"] == FREEZE
    assert written["what_was_wrong"] == "It said the freeze is March 12th."
    assert written["what_is_right"] == "The freeze moved to March 19th."
    assert second["correction"]["id"] == written["id"]
    assert second["correction"]["answer_id"] == first["answer_id"]

    # Recording it searched nothing, and cost no verification or routing
    # call: the script ran out exactly where the correction was recorded.
    assert second["searches"] == 0
    assert second["citations"] == []
    assert len(search.calls) == 1
    assert model.replies == []

    # The reply says what was recorded, rather than accepting it silently.
    assert second["answer"].startswith("I've recorded your correction")
    assert FREEZE in second["answer"]
    assert "It said the freeze is March 12th." in second["answer"]
    assert "The freeze moved to March 19th." in second["answer"]

    # A correction is not a gap in the record.
    assert recorded()["gaps"] == []


def test_the_correction_tool_is_offered_only_once_there_is_an_answer() -> None:
    """A first question is never offered a way to correct something."""
    model = ScriptedModel([*answers_freeze(), says(CORRECTION), corrects(number=1)])
    app = answering_app(model, StubSearch(result=found()))

    conversation(
        app,
        {"question": FREEZE},
        {"question": CORRECTION, "_thread_from": 0},
    )

    both = [TOOL_NAME, corrections.TOOL_NAME]
    # First turn: think, think, verify, route. Second: rewrite, think.
    assert model.offered == [[TOOL_NAME], [TOOL_NAME], [], [], [], both]
    # The turn offered the tool was shown what it could correct, by number.
    system = model.prompts[-1][0].content
    assert f'1. Asked: "{FREEZE}"' in system
    assert "The firmware freeze is March 12th." in system


def test_a_follow_up_question_is_not_recorded() -> None:
    """A doubtful question about an answer is answered, not recorded.

    The model is offered the correction tool on this turn and does not call
    it, so this is the graph's half of the rule: nothing is recorded unless
    the tool is called, and once the turn has searched the tool is no
    longer offered at all.
    """
    doubt = "Are you sure it's March 12th?"
    model = ScriptedModel(
        [
            *answers_freeze(),
            says("Is the firmware freeze really on March 12th?"),
            searches("firmware freeze date", call_id="call-2"),
            says("Yes: the schedule review put the freeze on March 12th."),
            verified(),
            answered(),
        ]
    )
    search = StubSearch(result=found())
    app = answering_app(model, search)

    _, second = conversation(
        app,
        {"question": FREEZE},
        {"question": doubt, "_thread_from": 0},
    )

    assert recorded()["corrections"] == []
    assert second["correction"] is None
    assert second["searches"] == 1
    assert second["answer"].startswith("Yes: the schedule review")
    both = [TOOL_NAME, corrections.TOOL_NAME]
    # Second turn: rewrite, think (both offered), think after the search
    # (search only), verify, route.
    assert model.offered[-5:] == [[], both, [TOOL_NAME], [], []]


def test_disagreement_that_says_nothing_specific_is_not_recorded() -> None:
    """A call with nothing in what is right records nothing, and asks.

    This is what a model that fires on "that's wrong" produces. A
    correction that does not say what is right is feedback at best, and it
    is not written to the corrections table.
    """
    model = ScriptedModel(
        [*answers_freeze(), says("That's wrong."), corrects(right="  ", number=1)]
    )
    app = answering_app(model, StubSearch(result=found()))

    _, second = conversation(
        app,
        {"question": FREEZE},
        {"question": "That's wrong.", "_thread_from": 0},
    )

    assert recorded()["corrections"] == []
    assert second["correction"] is None
    assert "What should it have said?" in second["answer"]
    assert "Nothing has been recorded" in second["answer"]


def test_a_correction_with_no_clear_referent_is_asked_about() -> None:
    """With two answers and no number, the user is asked which one.

    Once they say, the next turn records it, against the answer they named
    — and the turn that asked is not itself listed as an answer that could
    be corrected.
    """
    model = ScriptedModel(
        [
            *answers_freeze(),
            *answers_boards(),
            says(CORRECTION),
            corrects(),
            says("The first one."),
            corrects(number=1, call_id="fix-2"),
        ]
    )
    app = answering_app(model, StubSearch(result=found()))

    first, _, asked, settled = conversation(
        app,
        {"question": FREEZE},
        {"question": BOARDS, "_thread_from": 0},
        {"question": CORRECTION, "_thread_from": 0},
        {"question": "The first one.", "_thread_from": 0},
    )

    assert asked["correction"] is None
    assert asked["answer"].startswith("Which of my earlier answers")
    assert f'1. "{FREEZE}"' in asked["answer"]
    assert f'2. "{BOARDS}"' in asked["answer"]
    assert asked["searches"] == 0

    [written] = recorded()["corrections"]
    assert written["answer_id"] == first["answer_id"]
    assert settled["correction"]["id"] == written["id"]
    # The list the last turn was shown holds the two answers and not the
    # turn that asked which one was meant.
    system = model.prompts[-1][0].content
    assert f'2. Asked: "{BOARDS}"' in system
    assert "3. Asked:" not in system


def test_a_number_not_on_the_list_is_asked_about() -> None:
    """A number that names no earlier answer records nothing."""
    model = ScriptedModel([*answers_freeze(), says(CORRECTION), corrects(number=4)])
    app = answering_app(model, StubSearch(result=found()))

    _, second = conversation(
        app,
        {"question": FREEZE},
        {"question": CORRECTION, "_thread_from": 0},
    )

    assert recorded()["corrections"] == []
    assert second["answer"].startswith("Which of my earlier answers")


def test_with_one_earlier_answer_a_number_is_not_needed() -> None:
    """A correction with only one answer to correct cannot mean another."""
    model = ScriptedModel([*answers_freeze(), says(CORRECTION), corrects()])
    app = answering_app(model, StubSearch(result=found()))

    first, second = conversation(
        app,
        {"question": FREEZE},
        {"question": CORRECTION, "_thread_from": 0},
    )

    assert second["correction"]["answer_id"] == first["answer_id"]


def test_a_search_asked_for_alongside_a_correction_is_not_run() -> None:
    """A correction never reaches retrieval, even when the model asks it to."""
    both = AIMessage(
        "",
        tool_calls=[
            {"name": TOOL_NAME, "args": {"query": "freeze date"}, "id": "s"},
            *corrects(number=1).tool_calls,
        ],
    )
    model = ScriptedModel([*answers_freeze(), says(CORRECTION), both])
    search = StubSearch(result=found())
    app = answering_app(model, search)

    _, second = conversation(
        app,
        {"question": FREEZE},
        {"question": CORRECTION, "_thread_from": 0},
    )

    assert len(search.calls) == 1
    assert second["searches"] == 0
    assert second["correction"] is not None


# The rules below are the module's own, driven without a graph.


def an_answer(answer_id: str = "a1", question: str = FREEZE) -> Any:
    """Build one earlier answer."""
    return corrections.EarlierAnswer(
        answer_id=answer_id, question=question, answer="March 12th."
    )


def a_call(**args: Any) -> dict[str, Any]:
    """Build one call to the correction tool."""
    base = {"what_was_wrong": "March 12th.", "what_is_right": "March 19th."}
    return {"name": corrections.TOOL_NAME, "args": base | args, "id": "fix"}


def handled(call: dict[str, Any], answers: list[Any], recorder: Any) -> Any:
    """Run the handler to completion outside a graph."""
    return asyncio.run(corrections.handle(call, answers, recorder))


def test_an_answer_the_store_does_not_hold_is_reported_not_confirmed() -> None:
    """A correction that cannot be written says so rather than claiming it was."""

    async def refuses(answer_id: str, wrong: str, right: str) -> dict[str, Any]:
        raise UnknownAnswerError(answer_id)

    outcome = handled(a_call(), [an_answer()], refuses)

    assert outcome.correction is None
    assert outcome.reply.startswith("I could not record that correction")


def test_nothing_is_recorded_without_an_earlier_answer() -> None:
    """A call on a turn with nothing before it has nothing to attach to."""
    calls = []

    async def record(*args: Any) -> dict[str, Any]:
        calls.append(args)
        return {}

    outcome = handled(a_call(), [], record)

    assert calls == []
    assert outcome.correction is None
    assert "no earlier answer" in outcome.reply


def test_arguments_a_model_got_wrong_are_asked_about() -> None:
    """A call missing a required argument records nothing."""
    calls = []

    async def record(*args: Any) -> dict[str, Any]:
        calls.append(args)
        return {}

    outcome = handled(
        {"name": corrections.TOOL_NAME, "args": {"what_is_right": "x"}, "id": "f"},
        [an_answer()],
        record,
    )

    assert calls == []
    assert outcome.correction is None


@pytest.mark.parametrize(
    ("number", "expected"),
    [(None, None), (1, "a1"), (2, "a2"), (0, None), (3, None)],
)
def test_which_answer_a_number_names(number: int | None, expected: Any) -> None:
    """A number on the list names that answer; anything else asks."""
    answers = [an_answer("a1"), an_answer("a2", BOARDS)]
    written = []

    async def record(answer_id: str, wrong: str, right: str) -> dict[str, Any]:
        written.append(answer_id)
        return {"id": 1, "answer_id": answer_id}

    handled(a_call(answer_number=number), answers, record)

    assert written == ([] if expected is None else [expected])


def test_turns_that_recorded_or_asked_are_not_answers() -> None:
    """Only turns that answered something can be corrected."""
    call = corrects(number=1)
    messages = [
        HumanMessage(FREEZE, id="a1"),
        AIMessage("March 12th."),
        HumanMessage(CORRECTION, id="a2"),
        call,
        ToolMessage("Recorded.", tool_call_id="fix-1", name=corrections.TOOL_NAME),
        AIMessage("I've recorded your correction."),
        HumanMessage(BOARDS, id="a3"),
        AIMessage("Two weeks out."),
    ]

    listed = corrections.earlier_answers(messages)

    assert [answer.answer_id for answer in listed] == ["a1", "a3"]
    assert listed[0].answer == "March 12th."


def test_the_system_prompt_says_what_makes_a_turn_a_correction() -> None:
    """The definition lives in the prompt the model answers with."""
    prompt = load("answer")

    assert "## When the user corrects an earlier answer" in prompt
    assert corrections.TOOL_NAME in prompt
    assert "says specifically what is right instead" in prompt
    assert "Disagreement that does not say what is right" in prompt


def test_a_streamed_correction_reports_recording_rather_than_searching() -> None:
    """Streamed, a correcting turn reports no search, and ends on the record.

    The model here also asks for a search alongside the correction, which
    the graph drops, so the stream must not announce it either. The answer
    event carries the same body the JSON response does, correction and all.
    """
    both = AIMessage(
        "",
        tool_calls=[
            {"name": TOOL_NAME, "args": {"query": "freeze date"}, "id": "s"},
            *corrects(number=1).tool_calls,
        ],
    )
    model = ScriptedModel([*answers_freeze(), says(CORRECTION), both])
    search = StubSearch(result=found())
    app = answering_app(model, search)

    async def run() -> tuple[dict[str, Any], httpx.Response]:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://api.test"
            ) as client:
                asked = await client.post("/answer", json={"question": FREEZE})
                first = asked.json()
                streamed = await client.post(
                    "/answer",
                    json={"question": CORRECTION, "thread_id": first["thread_id"]},
                    headers=STREAM,
                )
                return first, streamed

    first, streamed = asyncio.run(run())
    stream = events(streamed)

    assert names(stream) == ["started", "drafting", "correcting", "answer"]
    assert len(search.calls) == 1
    answer = AnswerResponse.model_validate(dict(stream)["answer"])
    assert answer.searches == 0
    assert answer.correction is not None
    assert answer.correction.answer_id == first["answer_id"]
    assert answer.answer.startswith("I've recorded your correction")
    [written] = recorded()["corrections"]
    assert written["id"] == answer.correction.id
