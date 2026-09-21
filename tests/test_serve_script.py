"""Tests for the serve entry point.

Nothing binds a socket: uvicorn is replaced with a recorder, so the tests see
what it would have been asked to serve and with what. Opening the store and
the index is real; loading the models is not, so none of this needs the
models extra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from corpus_query.api.app import Resources, open_resources
from corpus_query.store.db import connect
from scripts.serve import main, parse_args


@dataclass
class FakeServer:
    """Stands in for ``uvicorn.run``, recording what it was handed."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, app, host: str, port: int) -> None:
        """Record the application and where it would have been bound."""
        self.calls.append({"app": app, "host": host, "port": port})


@pytest.fixture
def corpus(tmp_path, ingest):
    """Return a store on disk holding one ingested transcript."""
    database = tmp_path / "corpus.db"
    connection = connect(database)
    ingest(connection, "rev-b-schedule")
    connection.close()
    return database


@pytest.fixture
def no_model_loading(monkeypatch):
    """Open resources for real, but without loading the models."""
    opened: list[Resources] = []

    def open_without_models(database, index_dir, warm_models=True):
        resources = open_resources(database, index_dir, warm_models=False)
        opened.append(resources)
        return resources

    monkeypatch.setattr("scripts.serve.open_resources", open_without_models)
    yield
    for resources in opened:
        resources.close()


def test_defaults_bind_loopback(corpus, no_model_loading, tmp_path):
    """Serving with no arguments serves locally, on the usual port."""
    server = FakeServer()

    code = main(["--db", str(corpus), "--index", str(tmp_path / "chroma")], run=server)

    assert code == 0
    [call] = server.calls
    assert (call["host"], call["port"]) == ("127.0.0.1", 8000)


def test_host_and_port_are_passed_through(corpus, no_model_loading, tmp_path):
    """The bind address is the one asked for."""
    server = FakeServer()

    main(
        [
            "--db",
            str(corpus),
            "--index",
            str(tmp_path / "chroma"),
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
        ],
        run=server,
    )

    [call] = server.calls
    assert (call["host"], call["port"]) == ("0.0.0.0", 9000)


def test_a_missing_store_is_reported_and_nothing_is_served(tmp_path, capsys):
    """The corpus is checked before the socket, and the error says what to do."""
    server = FakeServer()

    code = main(
        ["--db", str(tmp_path / "nowhere.db"), "--index", str(tmp_path / "chroma")],
        run=server,
    )

    assert code == 1
    assert server.calls == []
    error = capsys.readouterr().err
    assert "no document store" in error
    assert "scripts/ingest.py" in error


def test_an_empty_store_is_reported(tmp_path, capsys):
    """A store with nothing in it fails loudly rather than serving nothing."""
    database = tmp_path / "corpus.db"
    connect(database).close()
    server = FakeServer()

    code = main(
        ["--db", str(database), "--index", str(tmp_path / "chroma")], run=server
    )

    assert code == 1
    assert server.calls == []
    assert "no chunks" in capsys.readouterr().err


def test_parse_args_defaults_to_the_projects_paths():
    """Run bare, it serves the store and index the rest of the project uses."""
    args = parse_args([])

    assert args.db.name == "corpus.db"
    assert "chroma" in str(args.index)


def test_the_corpus_and_the_usage_database_are_separate_files():
    """Conversations are not checkpointed into the committed corpus.

    The two used to be one file, which meant asking a question modified a
    binary that is under version control. They are separate defaults and
    separate flags now, and neither one follows the other.
    """
    args = parse_args([])
    assert args.usage_db != args.db
    assert args.usage_db.name == "usage.db"

    moved = parse_args(["--db", "/tmp/elsewhere/corpus.db"])
    assert moved.usage_db.name == "usage.db"
    assert moved.usage_db.parent != moved.db.parent
