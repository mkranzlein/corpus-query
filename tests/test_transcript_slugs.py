"""Tests for deriving a filename from a meeting subject."""

from __future__ import annotations

import pytest

from corpus_query.transcripts.slugs import FALLBACK_SLUG, slugify, unique_slug


@pytest.mark.parametrize(
    ("subject", "slug"),
    [
        ("Rev B schedule", "rev-b-schedule"),
        ("Q1 pricing: discount approvals", "q1-pricing-discount-approvals"),
        ("  Supplier lead times  ", "supplier-lead-times"),
        ("Yield — sensor line", "yield-sensor-line"),
        ("A/B test results", "a-b-test-results"),
        ("???", FALLBACK_SLUG),
    ],
)
def test_a_subject_becomes_a_lowercase_hyphenated_slug(subject: str, slug: str):
    assert slugify(subject) == slug


def test_an_unused_slug_is_left_alone():
    assert unique_slug("Rev B schedule", taken=["something-else"]) == "rev-b-schedule"


def test_a_collision_takes_a_numeric_suffix():
    assert unique_slug("Weekly sync", taken=["weekly-sync"]) == "weekly-sync-2"


def test_suffixes_keep_counting_past_the_first_collision():
    taken = ["weekly-sync", "weekly-sync-2", "weekly-sync-3"]
    assert unique_slug("Weekly sync", taken=taken) == "weekly-sync-4"


def test_the_same_subject_always_derives_the_same_slug():
    assert slugify("Rev B schedule") == slugify("REV b   SCHEDULE")
