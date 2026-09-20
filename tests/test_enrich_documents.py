"""Tests for reading a stored document back out for enrichment.

The reassembly is the part worth the attention: chunks overlap by a turn, so
a transcript put back together from them has to drop the repeat rather than
send the model a conversation in which people say things twice.
"""

from __future__ import annotations

import pytest

from corpus_query.enrich.documents import (
    StoredDocument,
    describe,
    document_text,
    ids_for_slugs,
    pending_ids,
    read_document,
)
from corpus_query.enrich.errors import EnrichmentError
from corpus_query.store.kinds import DOCX, SUMMARY, TRANSCRIPT

MANY_TURNS = [
    {"speaker": "Priya", "text": f"Point number {index} about the rev B boards."}
    for index in range(40)
]


def test_a_document_reads_back_with_its_header_and_its_turns(store, ingest):
    document_id = ingest(store, "rev-b-schedule")

    document = read_document(store, document_id)

    assert document.slug == "rev-b-schedule"
    assert document.source_kind == TRANSCRIPT
    assert document.title == "Rev B schedule"
    assert document.document_date == "2026-03-04"
    assert document.author is None
    assert document.attendees == ("Priya", "Marcus", "Sofia")
    assert document.text.splitlines()[0].startswith("[Priya]: Where are we")


def test_the_transcript_is_reassembled_without_the_chunk_overlap(store, ingest):
    document_id = ingest(store, "long", turns=MANY_TURNS)
    (chunks,) = store.execute(
        "SELECT count(*) FROM chunks WHERE document_id = ?", (document_id,)
    ).fetchone()

    lines = document_text(store, document_id).splitlines()

    assert chunks > 1, "the fixture needs enough turns to produce overlap"
    assert len(lines) == len(MANY_TURNS)
    assert len(set(lines)) == len(lines)
    assert lines[0].endswith("Point number 0 about the rev B boards.")
    assert lines[-1].endswith("Point number 39 about the rev B boards.")


def test_a_summary_chunk_is_not_part_of_the_transcript(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    store.execute(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, word_count, location,
             span_start, span_end, kind)
        VALUES (?, 99, 'A summary of the meeting.', 5, 'summary', NULL, NULL, ?)
        """,
        (document_id, SUMMARY),
    )

    assert "A summary of the meeting." not in document_text(store, document_id)


def test_a_document_rendered_for_a_prompt_reads_like_the_document(store, ingest):
    document = read_document(store, ingest(store, "rev-b-schedule"))

    rendered = describe(document)

    assert rendered.startswith("**Subject:** Rev B schedule")
    assert "**Attendees:** Priya, Marcus, Sofia" in rendered
    assert rendered.endswith(document.text)


def test_a_single_author_document_is_rendered_with_its_author(store, ingest):
    document = read_document(store, ingest(store, "rev-b-schedule"))
    authored = StoredDocument(
        id=document.id,
        slug="thermal-review",
        source_kind=DOCX,
        title="Thermal review",
        document_date="2026-03-04",
        author="Devon",
        attendees=(),
        text=document.text,
    )

    rendered = describe(authored)

    assert rendered.startswith("**Title:** Thermal review")
    assert "**Author:** Devon" in rendered
    assert "Attendees" not in rendered


def test_only_documents_without_a_summary_are_pending(store, ingest):
    first = ingest(store, "first")
    second = ingest(store, "second", subject="Tooling sync")
    store.execute("UPDATE documents SET summary = 'Done.' WHERE id = ?", (first,))

    assert pending_ids(store) == [second]


def test_documents_can_be_named_by_slug(store, ingest):
    ingest(store, "first")
    second = ingest(store, "second", subject="Tooling sync")

    assert ids_for_slugs(store, ["second"]) == [second]


def test_naming_a_document_that_does_not_exist_is_an_error(store, ingest):
    ingest(store, "first")

    with pytest.raises(EnrichmentError, match="no document with the slug 'second'"):
        ids_for_slugs(store, ["second"])


def test_reading_a_document_that_does_not_exist_is_an_error(store):
    with pytest.raises(EnrichmentError, match="no document with the id 7"):
        read_document(store, 7)


def test_a_document_with_no_chunks_cannot_be_enriched(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    store.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    with pytest.raises(EnrichmentError, match="no chunks to enrich"):
        read_document(store, document_id)
