"""Fixtures shared by the tests.

The enrichment fixtures here never reach a model. ``fake_client`` stands in
for the Bedrock client, records what it was asked, and answers with
already-valid structured output, so a test asserts on the request that would
have been sent and on what is done with the response.

It answers both ways the project asks a question: ``messages.parse`` for the
short passes, and ``messages.stream`` for the one response long enough to
need streaming. Both hand back the same fake message, since what a caller
does with it is the same either way.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from corpus_query.enrich.schema import (
    DocumentSummary,
    PriorityAssessment,
    TopicAssignment,
    TopicMerge,
    TopicMerges,
)
from corpus_query.ingest.chunk import chunk_turns
from corpus_query.ingest.pipeline import write_document
from corpus_query.store.db import connect
from corpus_query.transcripts.parse import parse_transcript
from corpus_query.transcripts.render import render_meeting
from corpus_query.transcripts.roster import DEFAULT_ROSTER_FILE
from corpus_query.transcripts.schema import Meeting

REPO_ROOT = Path(__file__).resolve().parents[1]

_MEETING: dict[str, Any] = {
    "subject": "Rev B schedule",
    "date": "2026-03-04",
    "attendees": ["Priya", "Marcus", "Sofia"],
    "turns": [
        {"speaker": "Priya", "text": "Where are we on the rev B boards?"},
        {"speaker": "Marcus", "text": "Two weeks out, assuming the connectors land."},
    ],
    "decisions": ["Hold the rev B date and re-check the connector lead time."],
    "action_items": [
        {"assignee": "Marcus", "task": "Confirm the connector lead time with Devon."}
    ],
}


@pytest.fixture
def roster_path() -> Path:
    """Return the committed roster, found without depending on the cwd."""
    return REPO_ROOT / DEFAULT_ROSTER_FILE


@pytest.fixture
def make_meeting() -> Callable[..., Meeting]:
    """Return a factory that builds a valid meeting, with fields overridden.

    Sofia attends without speaking and without owning an action item, so the
    default meeting exercises both of those allowances on its own.
    """

    def factory(**overrides: Any) -> Meeting:
        return Meeting.model_validate(_MEETING | overrides)

    return factory


#: A summary that satisfies the schema: more than one sentence, fewer than
#: six. Tests that care about the text override it.
CANNED_SUMMARY = (
    "The team works through the rev B board schedule and the connector lead "
    "time behind it. They hold the date and agree to confirm the lead time "
    "with the supplier."
)


@dataclass
class Call:
    """One request a fake client was asked to make."""

    model: str
    prompt: str
    output_format: type
    max_tokens: int
    temperature: float | None
    streamed: bool


@dataclass
class FakeClient:
    """Stands in for the Bedrock client, without a network.

    ``respond`` is given the prompt and the response type and returns what
    the model would have parsed, or ``None`` for a response that carried no
    structured output at all.
    """

    respond: Callable[[str, type], Any]
    stop_reason: str = "end_turn"
    calls: list[Call] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.messages = _FakeMessages(self)

    def prompts(self, output_format: type) -> list[str]:
        """Return the prompts sent for one response type, in order."""
        return [
            call.prompt for call in self.calls if call.output_format is output_format
        ]


@dataclass
class _FakeMessages:
    """The ``client.messages`` namespace, with the two calls in use on it."""

    client: FakeClient

    def parse(self, *, model, max_tokens, messages, output_format, **kwargs):
        """Record the request and answer it from the client's responder."""
        return self._record(
            model, max_tokens, messages, output_format, kwargs, streamed=False
        )

    def stream(self, *, model, max_tokens, messages, output_format, **kwargs):
        """Do the same, behind the context manager a stream is used through."""
        return _FakeStream(
            self._record(
                model, max_tokens, messages, output_format, kwargs, streamed=True
            )
        )

    def _record(self, model, max_tokens, messages, output_format, kwargs, streamed):
        """Log one request and build the message that answers it."""
        prompt = messages[-1]["content"]
        self.client.calls.append(
            Call(
                model=model,
                prompt=prompt,
                output_format=output_format,
                max_tokens=max_tokens,
                temperature=(kwargs.get("extra_body") or {}).get("temperature"),
                streamed=streamed,
            )
        )
        return _FakeMessage(
            parsed_output=self.client.respond(prompt, output_format),
            model=model,
            stop_reason=self.client.stop_reason,
        )


@dataclass
class _FakeMessage:
    """What a request hands back, parsed."""

    parsed_output: Any
    model: str = "us.anthropic.claude-sonnet-4-6"
    stop_reason: str = "end_turn"
    id: str = "msg_fake123"


@dataclass
class _FakeStream:
    """The context manager ``messages.stream`` is used through."""

    message: _FakeMessage

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def get_final_message(self) -> _FakeMessage:
        """Return the finished message, as draining a real stream would."""
        return self.message


def canned(
    summary: str | Callable[[str], str] = CANNED_SUMMARY,
    topics: Sequence[str] | Callable[[str], Sequence[str]] = ("Firmware",),
    time_sensitivity: str = "near_term",
    business_impact: str = "moderate",
    merges: Sequence[TopicMerge] = (),
) -> Callable[[str, type], Any]:
    """Build a responder that answers every pass with valid output.

    Args:
        summary: The summary to answer with, or a function of the prompt.
        topics: The topics to answer with, or a function of the prompt.
        time_sensitivity: The value the priority pass answers with.
        business_impact: The value the priority pass answers with.
        merges: What the dedupe pass proposes.

    Returns:
        A responder for :class:`FakeClient`.
    """

    def respond(prompt: str, output_format: type) -> Any:
        if output_format is DocumentSummary:
            text = summary(prompt) if callable(summary) else summary
            return DocumentSummary(summary=text)
        if output_format is TopicAssignment:
            chosen = topics(prompt) if callable(topics) else topics
            return TopicAssignment(topics=list(chosen))
        if output_format is PriorityAssessment:
            return PriorityAssessment(
                time_sensitivity=time_sensitivity, business_impact=business_impact
            )
        if output_format is TopicMerges:
            return TopicMerges(merges=list(merges))
        raise AssertionError(f"unexpected response type {output_format}")

    return respond


@pytest.fixture
def fake_client() -> Callable[..., FakeClient]:
    """Return a factory for a client that answers without calling anything."""

    def factory(respond: Callable[[str, type], Any] | None = None, **overrides):
        return FakeClient(respond=respond or canned(**overrides))

    return factory


@pytest.fixture
def fake_embedder() -> tuple[Callable[[Sequence[str]], Any], str]:
    """Return an embedding function and the model id to record with it.

    The vectors are deterministic and three-dimensional: enough to prove a
    blob round-trips and that one vector per chunk was written, without
    loading a model.
    """

    def embed(texts: Sequence[str]) -> Any:
        return np.array(
            [[float(len(text)), float(index), 1.0] for index, text in enumerate(texts)],
            dtype=np.float32,
        )

    return embed, "fake-embedder-v1"


@pytest.fixture
def store() -> sqlite3.Connection:
    """Return an open, empty document store in memory."""
    connection = connect(":memory:")
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def ingest(make_meeting) -> Callable[..., int]:
    """Return a factory that ingests one meeting straight into a store.

    It goes through render, parse, and chunk rather than inserting rows by
    hand, so the chunks a test enriches are the chunks ingestion produces,
    overlap and all.
    """

    def factory(connection: sqlite3.Connection, slug: str, **overrides: Any) -> int:
        meeting = make_meeting(**overrides)
        markdown = render_meeting(meeting)
        transcript = parse_transcript(markdown, source=f"{slug}.md")
        chunks = chunk_turns(transcript.turns)
        result = write_document(
            connection, slug, f"data/transcripts/{slug}.md", transcript, chunks
        )
        return result.document_id

    return factory
