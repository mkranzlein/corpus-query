"""Tests for the category list and what documents are filed under it."""

from __future__ import annotations

import pytest

from corpus_query.enrich.errors import EnrichmentError
from corpus_query.enrich.topics import (
    DEFAULT_TOPICS_FILE,
    NO_CATEGORIES,
    assign_topics,
    describe_categories,
    list_categories,
    read_seed_topics,
    seed_categories,
)
from tests.conftest import REPO_ROOT


def filed(connection, document_id) -> list[str]:
    """Return the categories a document is filed under, alphabetically."""
    return [
        row["name"]
        for row in connection.execute(
            """
            SELECT t.name FROM document_topics dt
            JOIN topics t ON t.id = dt.topic_id
            WHERE dt.document_id = ?
            ORDER BY t.name
            """,
            (document_id,),
        )
    ]


def test_the_seed_list_is_committed_rather_than_invented_per_run():
    names = read_seed_topics(REPO_ROOT / DEFAULT_TOPICS_FILE)

    assert len(names) > 5
    assert "Supply Chain" in names
    assert len({name.casefold() for name in names}) == len(names)


def test_a_missing_seed_list_is_an_error(tmp_path):
    with pytest.raises(EnrichmentError, match="Could not read the seed categories"):
        read_seed_topics(tmp_path / "absent.md")


def test_a_seed_list_with_no_categories_is_an_error(tmp_path):
    path = tmp_path / "topics.md"
    path.write_text("# Seed Categories\n\nNothing here yet.\n", encoding="utf-8")

    with pytest.raises(EnrichmentError, match="lists no categories"):
        read_seed_topics(path)


def test_a_seed_list_naming_a_category_twice_is_an_error(tmp_path):
    path = tmp_path / "topics.md"
    path.write_text("- Supply Chain\n- supply chain\n", encoding="utf-8")

    with pytest.raises(EnrichmentError, match="same category more than once"):
        read_seed_topics(path)


def test_seeding_twice_adds_the_categories_once(store):
    assert seed_categories(store, ["Firmware", "Pricing"]) == ["Firmware", "Pricing"]
    assert seed_categories(store, ["Firmware", "Pricing"]) == []
    assert list_categories(store) == ["Firmware", "Pricing"]


def test_seeding_ignores_case_when_deciding_what_is_new(store):
    seed_categories(store, ["Supply Chain"])

    assert seed_categories(store, ["supply chain"]) == []


def test_a_document_is_filed_under_the_categories_chosen_for_it(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    seed_categories(store, ["Firmware", "Supply Chain"])

    assert assign_topics(store, document_id, ["Firmware", "Supply Chain"]) == [
        "Firmware",
        "Supply Chain",
    ]
    assert filed(store, document_id) == ["Firmware", "Supply Chain"]


def test_a_category_spelled_differently_does_not_become_a_second_one(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    seed_categories(store, ["Supply Chain"])

    assert assign_topics(store, document_id, ["supply chain"]) == ["Supply Chain"]
    assert list_categories(store) == ["Supply Chain"]


def test_a_category_that_fits_nothing_on_the_list_is_created(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    seed_categories(store, ["Firmware"])

    assign_topics(store, document_id, ["Patent Filings"])

    assert list_categories(store) == ["Firmware", "Patent Filings"]


def test_refiling_a_document_replaces_what_it_was_filed_under(store, ingest):
    document_id = ingest(store, "rev-b-schedule")
    assign_topics(store, document_id, ["Firmware", "Pricing"])

    assign_topics(store, document_id, ["Pricing"])

    assert filed(store, document_id) == ["Pricing"]


def test_categories_are_listed_alphabetically_rather_than_by_when_made(store):
    seed_categories(store, ["Pricing", "Firmware"])

    assert list_categories(store) == ["Firmware", "Pricing"]


def test_the_category_list_is_rendered_as_bullets_for_a_prompt():
    assert describe_categories(["Firmware", "Pricing"]) == "- Firmware\n- Pricing"
    assert describe_categories([]) == NO_CATEGORIES
