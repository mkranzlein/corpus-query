"""Tests for enriching and searching a Word document.

A Word document is not a meeting, and the difference has to survive the trip
from the store to the prompt: a model asked to summarize it should be shown a
title and an author rather than a subject and a list of attendees who are not
there. No model is called — the client is the fake from ``conftest``, which
answers with structured output that is already valid — so what is checked is
the prompt that would have been sent and what is done with the answer.

The search at the end closes the loop: a chunk cut out of a heading section
comes back from retrieval carrying the author and the heading path a citation
needs.
"""

from __future__ import annotations

import numpy as np
import pytest

from corpus_query.enrich.documents import describe, read_document
from corpus_query.enrich.pipeline import enrich_document
from corpus_query.enrich.schema import DocumentSummary, TopicAssignment
from corpus_query.ingest.pipeline import ingest_file
from corpus_query.retrieval import index as index_module
from corpus_query.retrieval.search import search
from corpus_query.store.kinds import DOCX
from tests.conftest import REPO_ROOT

MODEL = "test-model"

#: One of the committed documents. It is the deepest of the three, so what a
#: model is shown for it is the awkward case rather than the easy one.
REPORT = REPO_ROOT / "data" / "office" / "xt-9-rev-b-thermal-qualification-report.docx"


@pytest.fixture
def report(store, monkeypatch):
    """Ingest the committed thermal report and return its document id."""
    monkeypatch.chdir(REPO_ROOT)
    return ingest_file(store, REPORT).document_id


def test_a_word_document_reads_back_with_its_author_and_no_attendees(store, report):
    document = read_document(store, report)

    assert document.source_kind == DOCX
    assert document.author == "Sofia"
    assert document.attendees == ()
    assert document.title == "XT-9 Rev B Thermal Qualification Report"
    assert document.document_date == "2026-03-12"


def test_the_prompt_shows_a_written_document_rather_than_a_meeting(store, report):
    rendered = describe(read_document(store, report))

    assert rendered.startswith("**Title:** XT-9 Rev B Thermal Qualification Report")
    assert "**Author:** Sofia" in rendered
    assert "Attendees" not in rendered
    assert "Thermal Chamber Results" in rendered, (
        "the headings are part of the document a model is shown"
    )


def test_the_document_a_model_sees_is_the_document_in_order(store, report):
    text = read_document(store, report).text

    lines = text.splitlines()
    assert lines[0] == "Scope of This Qualification"
    # Blank lines are left out: sections are separated by one, so counting
    # them would report a separator as a repeated block.
    blocks = [line for line in lines if line.strip()]
    assert len(blocks) == len(set(blocks)), "no block is shown to the model twice"
    assert lines.index("Findings") > lines.index("Test Method")


def test_enriching_fills_the_summary_topics_and_priority(
    store, report, fake_client, fake_embedder
):
    embed, embedding_model_id = fake_embedder
    client = fake_client(
        summary="Sofia qualifies the compensation firmware. It holds to 60 C.",
        topics=["Firmware", "Quality"],
        time_sensitivity="near_term",
        business_impact="significant",
    )

    result = enrich_document(
        store,
        client,
        MODEL,
        report,
        embed=embed,
        embedding_model_id=embedding_model_id,
    )

    row = store.execute(
        """
        SELECT summary, time_sensitivity, business_impact
        FROM documents WHERE id = ?
        """,
        (report,),
    ).fetchone()
    assert row["summary"] == result.summary
    assert row["time_sensitivity"] == "near_term"
    assert row["business_impact"] == "significant"
    assert result.topics == ("Firmware", "Quality")
    (unembedded,) = store.execute(
        "SELECT count(*) FROM chunks WHERE document_id = ? AND embedding IS NULL",
        (report,),
    ).fetchone()
    assert unembedded == 0


def test_the_summary_and_topic_passes_are_shown_the_document_itself(
    store, report, fake_client, fake_embedder
):
    embed, embedding_model_id = fake_embedder
    client = fake_client()

    enrich_document(
        store,
        client,
        MODEL,
        report,
        embed=embed,
        embedding_model_id=embedding_model_id,
    )

    [summary_prompt] = client.prompts(DocumentSummary)
    [topics_prompt] = client.prompts(TopicAssignment)
    for prompt in (summary_prompt, topics_prompt):
        assert "**Author:** Sofia" in prompt
        assert "Chamber B, 60 °C Soak" in prompt
        assert "[Priya]:" not in prompt, "a written document has no speakers"


def test_a_search_returns_a_word_chunk_with_its_author_and_heading_path(
    store, report, fake_client, fake_embedder, tmp_path
):
    embed, embedding_model_id = fake_embedder
    enrich_document(
        store,
        fake_client(),
        MODEL,
        report,
        embed=embed,
        embedding_model_id=embedding_model_id,
    )
    collection = index_module.build_index(store, tmp_path / "chroma")

    def embed_query(texts):
        return np.array([[1.0, 0.0, 0.0] for _ in texts], dtype=np.float32)

    def rerank(query, documents):
        words = set(query.lower().split())
        return [float(len(words & set(text.lower().split()))) for text in documents]

    found = search(
        store,
        collection,
        "uncompensated mean error at 60 °C soak",
        embed=embed_query,
        rerank=rerank,
    )

    top = found.results[0]
    assert top.source_kind == DOCX
    assert top.author == "Sofia"
    assert " > " in top.location
    assert top.text in read_document(store, report).text
