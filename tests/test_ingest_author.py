"""Tests for resolving a document's author against the staff roster.

This is the one place that behavior is tested directly. Word, PowerPoint, and
Excel each carry their own tests that a document with a blank or unresolvable
author is refused, but those exercise the reader end to end; the matching
rules themselves — case-insensitive, returning the roster's own spelling —
belong here, once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from corpus_query.ingest.author import ROSTER_PATH, resolve_author
from corpus_query.ingest.reader import IngestError

SOME_FILE = Path("some-file.docx")


def test_the_author_resolves_case_insensitively_to_the_rosters_spelling(roster_path):
    assert resolve_author(SOME_FILE, "priya", roster_path) == "Priya"
    assert resolve_author(SOME_FILE, "PRIYA", roster_path) == "Priya"
    assert resolve_author(SOME_FILE, "Priya", roster_path) == "Priya"


def test_a_blank_author_is_refused(roster_path):
    with pytest.raises(IngestError, match="names no author"):
        resolve_author(SOME_FILE, "", roster_path)


def test_a_missing_author_is_refused(roster_path):
    with pytest.raises(IngestError, match="names no author"):
        resolve_author(SOME_FILE, None, roster_path)


def test_an_author_not_on_the_roster_is_refused(roster_path):
    with pytest.raises(IngestError, match="not on the roster"):
        resolve_author(SOME_FILE, "Gwendolyn", roster_path)


def test_the_error_names_the_file_and_the_roster(roster_path):
    with pytest.raises(IngestError, match=r"some-file\.docx.*roster"):
        resolve_author(SOME_FILE, "Gwendolyn", roster_path)


def test_an_unreadable_roster_is_refused(tmp_path):
    missing = tmp_path / "no-such-roster.md"

    with pytest.raises(IngestError, match=r"some-file\.docx.*roster"):
        resolve_author(SOME_FILE, "Priya", missing)


def test_the_default_roster_is_found_from_the_package_regardless_of_cwd(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)

    assert resolve_author(SOME_FILE, "priya") == "Priya"


def test_the_default_roster_path_is_the_committed_roster(roster_path):
    assert ROSTER_PATH == roster_path
