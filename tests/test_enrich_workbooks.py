"""Tests for enriching an ingested workbook.

Nothing here reaches a model: the client is the fake from ``conftest``, and
what is checked is the text a workbook is put back together into before it
is sent, and that the pass writes what it writes for any other document.

The reassembly is the part worth the attention. A workbook's chunks are not
shaped like a transcript's — its windows do not overlap, they carry a
repeated header, and their row numbers start again at the top of every sheet
— so the arithmetic that drops a transcript's overlap has to leave them
alone, and the per-sheet summaries have to stay out of the text entirely
rather than be read back as if they were rows.
"""

from __future__ import annotations

import pytest

from corpus_query.enrich.documents import document_text, read_document
from corpus_query.enrich.pipeline import enrich_document
from corpus_query.enrich.schema import DocumentSummary
from corpus_query.ingest.pipeline import ingest_file
from corpus_query.store.kinds import SHEET_SUMMARY, XLSX
from tests.conftest import REPO_ROOT

MODEL = "test-model"
WORKBOOK = REPO_ROOT / "data" / "office" / "q1-sales-pipeline.xlsx"


@pytest.fixture
def workbook_id(store):
    """Ingest the multi-sheet workbook and return its document id."""
    return ingest_file(store, WORKBOOK).document_id


def test_every_row_window_is_in_the_text_the_model_is_shown(store, workbook_id):
    text = document_text(store, workbook_id)

    windows = store.execute(
        "SELECT text FROM chunks WHERE document_id = ? AND kind = 'row_window'",
        (workbook_id,),
    ).fetchall()

    assert windows
    for row in windows:
        assert row["text"] in text


def test_a_sheet_summary_is_not_part_of_the_workbook(store, workbook_id):
    summaries = store.execute(
        "SELECT text FROM chunks WHERE document_id = ? AND kind = ?",
        (workbook_id, SHEET_SUMMARY),
    ).fetchall()

    text = document_text(store, workbook_id)

    assert summaries, "the fixture needs a workbook with per-sheet summaries"
    for row in summaries:
        assert row["text"] not in text


def test_every_row_of_the_workbook_appears_once(store, workbook_id):
    lines = [
        line
        for line in document_text(store, workbook_id).splitlines()
        if line.startswith("| OPP-")
    ]

    assert len(lines) == 45
    assert len(set(lines)) == len(lines)


def test_two_windows_do_not_run_together_into_one_table(store, workbook_id):
    text = document_text(store, workbook_id)

    assert "\n\n**Sheet:** " in text


def test_a_workbook_is_rendered_with_its_author(store, workbook_id):
    document = read_document(store, workbook_id)

    assert document.source_kind == XLSX
    assert document.author == "Jamal"
    assert document.attendees == ()


def test_enriching_a_workbook_writes_its_summary_and_embeds_its_chunks(
    store, workbook_id, fake_client, fake_embedder
):
    embed, model_id = fake_embedder
    client = fake_client()

    result = enrich_document(
        store,
        client,
        MODEL,
        workbook_id,
        embed=embed,
        embedding_model_id=model_id,
    )

    row = store.execute(
        "SELECT summary FROM documents WHERE id = ?", (workbook_id,)
    ).fetchone()
    (unembedded,) = store.execute(
        "SELECT count(*) FROM chunks WHERE document_id = ? AND embedding IS NULL",
        (workbook_id,),
    ).fetchone()

    assert row["summary"] == result.summary
    assert unembedded == 0
    assert "Open Opportunities" in client.prompts(DocumentSummary)[0]
