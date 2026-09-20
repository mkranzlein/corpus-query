"""Tests for merging near-duplicate categories.

The case worth the most attention is a document already filed under both the
name being merged away and the name that survives. ``document_topics`` has
``(document_id, topic_id)`` as its primary key, so repointing that row onto
the surviving category collides with the row the document already has. If
that is not handled, one such document fails the whole merge.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from corpus_query.enrich.dedupe import apply_merges
from corpus_query.enrich.errors import EnrichmentError
from corpus_query.enrich.schema import TopicMerge
from corpus_query.enrich.topics import assign_topics, list_categories


def filings(connection) -> set[tuple[int, str]]:
    """Return every filing as a ``(document_id, category name)`` pair."""
    return {
        (row["document_id"], row["name"])
        for row in connection.execute(
            """
            SELECT dt.document_id, t.name FROM document_topics dt
            JOIN topics t ON t.id = dt.topic_id
            """
        )
    }


def test_a_merge_repoints_filings_onto_the_surviving_category(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    assign_topics(store, document_id, ["Supply Chain Risk"])
    store.execute("INSERT INTO topics (name) VALUES ('Supply Chain')")

    [merged] = apply_merges(
        store, [TopicMerge(keep="Supply Chain", merge=["Supply Chain Risk"])]
    )

    assert merged.repointed == 1
    assert merged.collapsed == 0
    assert filings(store) == {(document_id, "Supply Chain")}


def test_a_document_filed_under_both_keeps_one_row_rather_than_colliding(store, ingest):
    both = ingest(store, "both")
    one = ingest(store, "one", subject="Supplier review")
    assign_topics(store, both, ["Supply Chain", "Supply Chain Risk"])
    assign_topics(store, one, ["Supply Chain Risk"])

    [merged] = apply_merges(
        store, [TopicMerge(keep="Supply Chain", merge=["Supply Chain Risk"])]
    )

    assert merged.repointed == 1
    assert merged.collapsed == 1
    assert filings(store) == {(both, "Supply Chain"), (one, "Supply Chain")}


def test_a_merge_cannot_fold_the_surviving_category_into_itself():
    with pytest.raises(ValidationError, match="cannot be merged into itself"):
        TopicMerge(keep="Firmware", merge=["firmware"])


def test_the_merged_category_is_gone_from_the_list(store, ingest):
    assign_topics(store, ingest(store, "rev-b-schedule"), ["Hiring", "Recruiting"])

    apply_merges(store, [TopicMerge(keep="Hiring", merge=["Recruiting"])])

    assert list_categories(store) == ["Hiring"]


def test_several_groups_merge_in_one_pass(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    assign_topics(store, document_id, ["Supply Chain Risk", "Recruiting"])
    store.execute("INSERT INTO topics (name) VALUES ('Supply Chain')")
    store.execute("INSERT INTO topics (name) VALUES ('Hiring')")

    merged = apply_merges(
        store,
        [
            TopicMerge(keep="Supply Chain", merge=["Supply Chain Risk"]),
            TopicMerge(keep="Hiring", merge=["Recruiting"]),
        ],
    )

    assert [result.keep for result in merged] == ["Supply Chain", "Hiring"]
    assert filings(store) == {(document_id, "Supply Chain"), (document_id, "Hiring")}


def test_a_merge_matches_a_category_without_regard_to_case(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    assign_topics(store, document_id, ["Supply Chain", "Supply Chain Risk"])

    [merged] = apply_merges(
        store, [TopicMerge(keep="supply chain", merge=["SUPPLY CHAIN RISK"])]
    )

    assert merged.keep == "Supply Chain"
    assert merged.merged == ("Supply Chain Risk",)


def test_proposing_no_merges_changes_nothing(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    assign_topics(store, document_id, ["Firmware"])

    assert apply_merges(store, []) == []
    assert filings(store) == {(document_id, "Firmware")}


def test_a_merge_naming_a_category_that_does_not_exist_merges_nothing(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    assign_topics(store, document_id, ["Firmware", "Pricing"])

    with pytest.raises(EnrichmentError, match="not a category in the store"):
        apply_merges(
            store,
            [
                TopicMerge(keep="Firmware", merge=["Pricing"]),
                TopicMerge(keep="Sales", merge=["Discounts"]),
            ],
        )

    assert list_categories(store) == ["Firmware", "Pricing"]
    assert filings(store) == {(document_id, "Firmware"), (document_id, "Pricing")}


def test_a_category_named_in_two_groups_merges_nothing(store, ingest):
    assign_topics(store, ingest(store, "rev-b-schedule"), ["Firmware", "Pricing"])
    store.execute("INSERT INTO topics (name) VALUES ('Sales')")

    with pytest.raises(EnrichmentError, match="more than one merge"):
        apply_merges(
            store,
            [
                TopicMerge(keep="Firmware", merge=["Pricing"]),
                TopicMerge(keep="Sales", merge=["Pricing"]),
            ],
        )

    assert list_categories(store) == ["Firmware", "Pricing", "Sales"]
