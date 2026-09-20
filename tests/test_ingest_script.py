"""Tests for the ingest entry point.

Nothing here is mocked. Ingestion is deterministic offline code, so the script
is run against transcripts written into a temporary directory and a store in a
temporary file, and the tests look at what ended up in it.
"""

from __future__ import annotations

import pytest

from corpus_query.store.db import connect
from corpus_query.transcripts.render import render_meeting
from scripts.ingest import main, parse_args


@pytest.fixture
def corpus(tmp_path, make_meeting):
    """Return a factory that writes transcripts into a temporary directory."""
    directory = tmp_path / "transcripts"
    directory.mkdir()

    def factory(slug: str, **overrides):
        path = directory / f"{slug}.md"
        path.write_text(render_meeting(make_meeting(**overrides)), encoding="utf-8")
        return path

    factory.directory = directory
    return factory


def slugs(path) -> set[str]:
    """Return every document slug in the store at ``path``."""
    connection = connect(path)
    try:
        return {row["slug"] for row in connection.execute("SELECT slug FROM documents")}
    finally:
        connection.close()


def test_it_ingests_everything_in_the_directory(tmp_path, corpus):
    corpus("first")
    corpus("second", subject="Tooling sync")
    db = tmp_path / "corpus.db"

    assert main(["--dir", str(corpus.directory), "--db", str(db)]) == 0
    assert slugs(db) == {"first", "second"}


def test_it_ingests_only_the_files_named(tmp_path, corpus):
    corpus("first")
    named = corpus("second", subject="Tooling sync")
    db = tmp_path / "corpus.db"

    assert main([str(named), "--db", str(db)]) == 0
    assert slugs(db) == {"second"}


def test_running_it_twice_does_not_duplicate(tmp_path, corpus):
    corpus("first")
    db = tmp_path / "corpus.db"
    arguments = ["--dir", str(corpus.directory), "--db", str(db)]

    assert main(arguments) == 0
    assert main(arguments) == 0

    connection = connect(db)
    try:
        (documents,) = connection.execute("SELECT count(*) FROM documents").fetchone()
    finally:
        connection.close()
    assert documents == 1


def test_an_empty_directory_is_an_error(tmp_path, capsys):
    empty = tmp_path / "nothing"
    empty.mkdir()
    assert main(["--dir", str(empty), "--db", str(tmp_path / "corpus.db")]) == 1
    assert "no transcripts" in capsys.readouterr().err


def test_a_bad_file_fails_the_run_but_not_the_good_files(tmp_path, corpus, capsys):
    corpus("first")
    (corpus.directory / "notes.md").write_text("Just some notes.\n", encoding="utf-8")
    db = tmp_path / "corpus.db"

    assert main(["--dir", str(corpus.directory), "--db", str(db)]) == 1
    assert "notes.md" in capsys.readouterr().err
    assert slugs(db) == {"first"}


def test_the_database_file_is_created_along_with_its_directory(tmp_path, corpus):
    corpus("first")
    db = tmp_path / "nested" / "corpus.db"
    assert main(["--dir", str(corpus.directory), "--db", str(db)]) == 0
    assert db.is_file()


def test_the_defaults_point_at_the_committed_locations():
    arguments = parse_args([])
    assert arguments.directory.as_posix() == "data/transcripts"
    assert arguments.db.as_posix() == "data/corpus.db"
