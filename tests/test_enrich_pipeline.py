"""Tests for enriching a corpus.

The client is a fake: it records the prompts it was given and answers with
structured output that is already valid. Nothing here reaches a model, so
what is checked is the request that would have been sent, what is done with
the response, and the two properties the pipeline exists to guarantee —
sequential processing and one transaction per document.
"""

from __future__ import annotations

import pytest

from corpus_query.store.kinds import SUMMARY
from corpus_query.enrich.errors import EnrichmentError
from corpus_query.enrich.pipeline import (
    dedupe_categories,
    enrich_document,
    enrich_documents,
    seed_store,
)
from corpus_query.enrich.schema import (
    DocumentSummary,
    PriorityAssessment,
    TopicAssignment,
    TopicMerge,
)
from corpus_query.enrich.topics import DEFAULT_TOPICS_FILE, list_categories
from tests.conftest import REPO_ROOT, canned

MODEL = "test-model"


@pytest.fixture
def enrich(fake_embedder):
    """Return a helper that enriches one document with the fake embedder."""
    embed, model_id = fake_embedder

    def run(connection, client, document_id, **kwargs):
        return enrich_document(
            connection,
            client,
            MODEL,
            document_id,
            embed=embed,
            embedding_model_id=model_id,
            **kwargs,
        )

    return run


@pytest.fixture
def enrich_all(fake_embedder):
    """Return a helper that enriches several documents with the fake embedder."""
    embed, model_id = fake_embedder

    def run(connection, client, document_ids, **kwargs):
        return enrich_documents(
            connection,
            client,
            MODEL,
            document_ids,
            embed=embed,
            embedding_model_id=model_id,
            **kwargs,
        )

    return run


def document_row(connection, document_id):
    """Return a document's enriched fields."""
    return connection.execute(
        "SELECT summary, time_sensitivity, business_impact FROM documents WHERE id = ?",
        (document_id,),
    ).fetchone()


def summary_chunks(connection, document_id):
    """Return a document's summary chunks, in order."""
    return connection.execute(
        """
        SELECT id, text, ordinal, location, span_start, span_end, embedding
        FROM chunks WHERE document_id = ? AND kind = ? ORDER BY ordinal
        """,
        (document_id, SUMMARY),
    ).fetchall()


def test_enriching_writes_the_summary_and_both_priority_fields(
    store, ingest, fake_client, enrich
):
    document_id = ingest(store, "rev-b-schedule")
    client = fake_client(time_sensitivity="urgent", business_impact="critical")

    result = enrich(store, client, document_id)

    row = document_row(store, document_id)
    assert row["summary"] == result.summary
    assert row["time_sensitivity"] == "urgent"
    assert row["business_impact"] == "critical"


def test_the_summary_is_also_a_chunk_with_no_span(store, ingest, fake_client, enrich):
    document_id = ingest(store, "rev-b-schedule")

    result = enrich(store, client=fake_client(), document_id=document_id)

    [chunk] = summary_chunks(store, document_id)
    assert chunk["text"] == result.summary
    assert chunk["span_start"] is None
    assert chunk["span_end"] is None
    assert chunk["location"] == "summary"
    assert chunk["embedding"] is not None


def test_the_summary_chunk_is_searchable_like_any_other(
    store, ingest, fake_client, enrich
):
    document_id = ingest(store, "rev-b-schedule")

    enrich(
        store,
        fake_client(summary="Connector lead times slip. Nothing is settled."),
        document_id,
    )

    hits = store.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'connector'"
    ).fetchall()
    [chunk] = summary_chunks(store, document_id)
    assert chunk["id"] in {row["rowid"] for row in hits}


def test_every_chunk_including_the_summary_is_embedded(
    store, ingest, fake_client, enrich
):
    document_id = ingest(store, "rev-b-schedule")

    result = enrich(store, fake_client(), document_id)

    (unembedded,) = store.execute(
        "SELECT count(*) FROM chunks WHERE document_id = ? AND embedding IS NULL",
        (document_id,),
    ).fetchone()
    assert unembedded == 0
    assert result.embedded.written >= 2


def test_the_topics_chosen_are_filed_and_reported(store, ingest, fake_client, enrich):
    document_id = ingest(store, "rev-b-schedule")

    result = enrich(
        store, fake_client(topics=["Firmware", "Supply Chain"]), document_id
    )

    assert result.topics == ("Firmware", "Supply Chain")
    assert set(list_categories(store)) >= {"Firmware", "Supply Chain"}


def test_each_document_sees_the_categories_the_one_before_it_created(
    store, ingest, fake_client, enrich_all
):
    first = ingest(store, "first")
    second = ingest(store, "second", subject="Tooling sync")
    client = fake_client(topics=lambda prompt: ["Patent Filings"])

    enrich_all(store, client, [first, second])

    [_, later] = client.prompts(TopicAssignment)
    assert "- Patent Filings" in later, (
        "the second document was not shown the category the first one created"
    )


def test_documents_are_enriched_in_the_order_they_are_given(
    store, ingest, fake_client, enrich_all
):
    first = ingest(store, "first")
    second = ingest(store, "second", subject="Tooling sync")
    client = fake_client()

    done, failures = enrich_all(store, client, [second, first])

    assert [result.slug for result in done] == ["second", "first"]
    assert failures == []
    assert [call.model for call in client.calls] == [MODEL] * 6


def test_nothing_is_written_when_a_pass_fails(store, ingest, fake_client, enrich):
    document_id = ingest(store, "rev-b-schedule")

    def refuse(prompt, output_format):
        if output_format is PriorityAssessment:
            return None
        return canned()(prompt, output_format)

    with pytest.raises(EnrichmentError, match="no parsed structured output"):
        enrich(store, fake_client(refuse), document_id)

    assert document_row(store, document_id)["summary"] is None
    assert summary_chunks(store, document_id) == []
    assert store.execute("SELECT count(*) FROM document_topics").fetchone()[0] == 0


def test_a_priority_outside_the_vocabulary_leaves_the_document_unenriched(
    store, ingest, fake_client, enrich
):
    document_id = ingest(store, "rev-b-schedule")
    client = fake_client(time_sensitivity="quite soon")

    with pytest.raises(EnrichmentError, match="did not validate"):
        enrich(store, client, document_id)

    assert document_row(store, document_id)["summary"] is None


def test_one_failed_document_does_not_abandon_the_others(
    store, ingest, fake_client, enrich_all
):
    first = ingest(store, "first")
    second = ingest(store, "second", subject="Tooling sync")
    third = ingest(store, "third", subject="Pricing review")

    def fail_the_second(prompt, output_format):
        if "Tooling sync" in prompt and output_format is DocumentSummary:
            return None
        return canned()(prompt, output_format)

    done, failures = enrich_all(
        store, fake_client(fail_the_second), [first, second, third]
    )

    assert [result.slug for result in done] == ["first", "third"]
    assert [failure.slug for failure in failures] == ["second"]
    assert document_row(store, first)["summary"] is not None
    assert document_row(store, second)["summary"] is None
    assert document_row(store, third)["summary"] is not None


def test_a_document_that_cannot_be_read_is_reported_rather_than_raised(
    store, fake_client, enrich_all
):
    done, failures = enrich_all(store, fake_client(), [404])

    assert done == []
    assert failures[0].slug == "document 404"
    assert "no document with the id 404" in str(failures[0].error)


def test_re_enriching_replaces_the_summary_chunk_rather_than_adding_one(
    store, ingest, fake_client, enrich
):
    document_id = ingest(store, "rev-b-schedule")
    enrich(store, fake_client(), document_id)

    enrich(
        store, fake_client(summary="A newer summary. Still two sentences."), document_id
    )

    [chunk] = summary_chunks(store, document_id)
    assert chunk["text"] == "A newer summary. Still two sentences."
    assert chunk["embedding"] is not None, "the replacement chunk was left unembedded"


def test_re_enriching_does_not_recompute_the_embeddings_it_already_has(
    store, ingest, fake_client, enrich
):
    document_id = ingest(store, "rev-b-schedule")
    first = enrich(store, fake_client(), document_id)

    second = enrich(store, fake_client(), document_id)

    assert second.embedded.skipped == first.embedded.written - 1
    assert second.embedded.written == 1, "only the new summary chunk needs embedding"


def test_the_seed_list_is_in_the_store_before_the_first_document_is_filed(
    store, ingest, fake_client, enrich
):
    added = seed_store(store, REPO_ROOT / DEFAULT_TOPICS_FILE)
    client = fake_client()

    enrich(store, client, ingest(store, "rev-b-schedule"))

    assert "Supply Chain" in added
    assert "- Supply Chain" in client.prompts(TopicAssignment)[0]


def test_seeding_a_store_twice_adds_nothing_the_second_time(store):
    seed_store(store, REPO_ROOT / DEFAULT_TOPICS_FILE)

    assert seed_store(store, REPO_ROOT / DEFAULT_TOPICS_FILE) == []


def test_the_dedupe_pass_is_shown_the_whole_list_and_merges_what_it_names(
    store, ingest, fake_client, enrich_all
):
    first = ingest(store, "first")
    second = ingest(store, "second", subject="Supplier review")
    client = fake_client(
        topics=lambda prompt: (
            ["Supply Chain"] if "Rev B" in prompt else ["Supply Chain Risk"]
        )
    )
    enrich_all(store, client, [first, second])
    merging = fake_client(
        merges=[TopicMerge(keep="Supply Chain", merge=["Supply Chain Risk"])]
    )

    [merged] = dedupe_categories(store, merging, MODEL)

    assert "- Supply Chain Risk" in merging.calls[0].prompt
    assert merged.repointed == 1
    assert list_categories(store) == ["Supply Chain"]


def test_dedupe_does_nothing_when_there_are_no_categories(store, fake_client):
    client = fake_client()

    assert dedupe_categories(store, client, MODEL) == []
    assert client.calls == []
