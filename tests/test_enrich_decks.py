"""Tests for enriching a PowerPoint deck.

Nothing here reaches a model. The client is the fake from ``conftest``: it
records the prompt it would have sent and answers with structured output
that is already valid. What is checked is that a deck reassembled out of its
slide chunks reads like the deck — header fields, slide headings, and the
speaker notes that carry the claims — and that the passes fill the summary,
the topics, and the two priority fields for a deck as for any other format.
"""

from __future__ import annotations

import pytest

from corpus_query.enrich.documents import describe, read_document
from corpus_query.enrich.passes import summary_prompt
from corpus_query.enrich.pipeline import enrich_document
from corpus_query.ingest.decks import NOTES_LABEL, read_deck
from corpus_query.ingest.pipeline import write_document
from corpus_query.store.kinds import PPTX
from tests.conftest import REPO_ROOT

MODEL = "test-model"
DECK = REPO_ROOT / "data" / "office" / "q1-board-review.pptx"


@pytest.fixture
def deck_id(store, roster_path):
    """Ingest the committed board review deck and return its document id."""
    document = read_deck(DECK, roster_path=roster_path)
    return write_document(store, DECK.stem, DECK, document).document_id


def test_a_deck_reads_back_with_its_author_and_its_slides(store, deck_id):
    document = read_document(store, deck_id)

    assert document.source_kind == PPTX
    assert document.title == "Q1 2026 Board Review"
    assert document.document_date == "2026-04-02"
    assert document.author == "Priya"
    assert document.attendees == ()
    assert document.text.startswith("## Slide 1")


def test_the_reassembled_deck_keeps_every_slide_once(store, deck_id):
    text = read_document(store, deck_id).text

    headings = [line for line in text.splitlines() if line.startswith("## Slide ")]
    assert len(headings) == len(set(headings))
    assert headings[0] == "## Slide 1: Q1 2026 Board Review"
    assert "## Slide 6: Q2 Pipeline by Stage" in headings


def test_the_prompt_carries_the_header_the_slides_and_the_notes(store, deck_id):
    document = read_document(store, deck_id)

    rendered = describe(document)
    prompt = summary_prompt(document)

    assert rendered.startswith("**Title:** Q1 2026 Board Review")
    assert "**Author:** Priya" in rendered
    assert "**Attendees:**" not in rendered
    assert rendered in prompt
    assert NOTES_LABEL in prompt
    assert "$1.14 million against a $1.25 million plan" in prompt


def test_enriching_a_deck_fills_the_summary_topics_and_priority(
    store, deck_id, fake_client, fake_embedder
):
    embed, embedding_model_id = fake_embedder
    client = fake_client(
        topics=("Revenue and Pipeline",),
        time_sensitivity="urgent",
        business_impact="critical",
    )

    result = enrich_document(
        store,
        client,
        MODEL,
        deck_id,
        embed=embed,
        embedding_model_id=embedding_model_id,
    )

    row = store.execute(
        "SELECT summary, time_sensitivity, business_impact FROM documents WHERE id = ?",
        (deck_id,),
    ).fetchone()
    assert row["summary"] == result.summary
    assert row["time_sensitivity"] == "urgent"
    assert row["business_impact"] == "critical"
    assert result.topics == ("Revenue and Pipeline",)
    topics = [
        name
        for (name,) in store.execute(
            """
            SELECT topics.name FROM topics
            JOIN document_topics ON document_topics.topic_id = topics.id
            WHERE document_topics.document_id = ?
            """,
            (deck_id,),
        )
    ]
    assert topics == ["Revenue and Pipeline"]


def test_every_slide_chunk_is_embedded(store, deck_id, fake_client, fake_embedder):
    embed, embedding_model_id = fake_embedder

    enrich_document(
        store,
        fake_client(),
        MODEL,
        deck_id,
        embed=embed,
        embedding_model_id=embedding_model_id,
    )

    (missing,) = store.execute(
        "SELECT count(*) FROM chunks WHERE document_id = ? AND embedding IS NULL",
        (deck_id,),
    ).fetchone()
    assert missing == 0
