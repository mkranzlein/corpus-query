"""Tests for where the usage database lives.

The point of this module is that the running service's own record is not the
corpus, so what is worth asserting is that the two paths differ, that a fresh
clone needs no setup step before the file can be opened, and that the default
is resolved late enough to be redirected.
"""

from __future__ import annotations

from corpus_query.store import usage
from corpus_query.store.db import DEFAULT_DATABASE_FILE
from corpus_query.store.usage import DEFAULT_USAGE_DATABASE_FILE, usage_database


def test_the_usage_database_is_not_the_corpus() -> None:
    """The committed corpus and the local record of use are separate files."""
    assert DEFAULT_USAGE_DATABASE_FILE != DEFAULT_DATABASE_FILE


def test_resolving_makes_the_directory_but_not_the_file(tmp_path) -> None:
    """The directory is created; SQLite makes the file when it connects.

    Creating an empty file here would leave a zero-byte database behind for
    anything that resolved a path and then failed, which SQLite would later
    open as a valid empty database rather than report.
    """
    path = usage_database(tmp_path / "nested" / "deeper" / "usage.db")

    assert path.parent.is_dir()
    assert not path.exists()


def test_resolving_an_existing_directory_is_not_an_error(tmp_path) -> None:
    """Starting the service twice is the ordinary case, not a collision."""
    usage_database(tmp_path / "usage.db")
    path = usage_database(tmp_path / "usage.db")

    assert path.parent.is_dir()


def test_the_default_is_read_at_call_time(tmp_path, monkeypatch) -> None:
    """Redirecting the default takes effect on callers that already imported.

    This is what lets the suite send a forgotten agent's checkpoints to a
    temporary file. A default argument would have bound the original path
    when the calling module was imported, and patching would do nothing.
    """
    monkeypatch.setattr(usage, "DEFAULT_USAGE_DATABASE_FILE", tmp_path / "moved.db")

    assert usage_database() == tmp_path / "moved.db"
