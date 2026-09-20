"""Tests for the enrichment entry point.

The client and the embedder are both injected, so a run makes no call and
loads no model. What is checked is which documents the script selects, that
a dry run sends nothing at all, and what it reports when something fails.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from corpus_query.enrich.errors import EnrichmentError
from corpus_query.enrich.schema import (
    DocumentSummary,
    TopicAssignment,
    TopicMerge,
    TopicMerges,
)
from corpus_query.store.db import connect
from scripts.enrich import build_client, build_embedder, main, parse_args
from tests.conftest import canned

pytestmark = pytest.mark.usefixtures("no_env_file")


@pytest.fixture
def no_env_file(monkeypatch, tmp_path):
    """Point the script's env file somewhere empty.

    The client factory is injected in these tests, so nothing reads the
    settings — but a developer machine has a real ``.env`` sitting in the
    repository root, and a test should not depend on whether it is there.
    """
    monkeypatch.setattr("scripts.enrich.ENV_FILE", str(tmp_path / "absent.env"))


@pytest.fixture
def corpus(tmp_path, ingest):
    """Return a store on disk, with a factory for adding documents to it."""
    path = tmp_path / "corpus.db"

    def factory(*slugs):
        connection = connect(path)
        try:
            for index, slug in enumerate(slugs):
                ingest(connection, slug, subject=f"Meeting {index}")
        finally:
            connection.close()
        return path

    factory.path = path
    return factory


@pytest.fixture
def run(fake_embedder):
    """Return a helper that runs the script against a fake client."""
    embed, model_id = fake_embedder

    def factory(argv, client):
        return main(
            argv,
            client_factory=lambda env: client,
            embedder_factory=lambda: (embed, model_id),
        )

    return factory


def summaries(path):
    """Return every document's slug and summary."""
    connection = connect(path)
    try:
        return {
            row["slug"]: row["summary"]
            for row in connection.execute("SELECT slug, summary FROM documents")
        }
    finally:
        connection.close()


def test_the_default_run_enriches_everything_unenriched(
    corpus, fake_client, run, capsys
):
    path = corpus("first", "second")
    client = fake_client()

    assert run(["--db", str(path)], client) == 0

    assert all(summaries(path).values())
    assert "Enriched 2 of 2 documents" in capsys.readouterr().out


def test_a_document_that_already_has_a_summary_is_left_alone(
    corpus, fake_client, run, capsys
):
    path = corpus("first", "second")
    client = fake_client()
    run(["--db", str(path)], client)
    again = fake_client()

    assert run(["--db", str(path)], again) == 0

    assert again.calls == []
    assert "Nothing to enrich" in capsys.readouterr().out


def test_it_can_be_pointed_at_specific_documents(corpus, fake_client, run):
    path = corpus("first", "second")
    client = fake_client()

    assert run(["--db", str(path), "second"], client) == 0

    written = summaries(path)
    assert written["first"] is None
    assert written["second"]


def test_naming_a_document_that_does_not_exist_calls_nothing(
    corpus, fake_client, run, capsys
):
    path = corpus("first")
    client = fake_client()

    assert run(["--db", str(path), "third"], client) == 1

    assert client.calls == []
    assert "no document with the slug 'third'" in capsys.readouterr().err


def test_a_dry_run_prints_the_prompts_and_calls_nothing(
    corpus, fake_client, run, capsys
):
    path = corpus("first")
    client = fake_client()

    assert run(["--db", str(path), "--dry-run"], client) == 0

    out = capsys.readouterr().out
    assert client.calls == []
    assert "first: summary" in out
    assert "first: topics" in out
    assert "first: priority" in out
    assert "===== dedupe =====" in out
    assert summaries(path) == {"first": None}


def test_the_seed_categories_reach_the_topic_prompt(corpus, fake_client, run):
    path = corpus("first")
    client = fake_client()

    run(["--db", str(path)], client)

    assert "- Supply Chain" in client.prompts(TopicAssignment)[0]


def test_the_dedupe_pass_runs_at_the_end_and_is_reported(
    corpus, fake_client, run, capsys
):
    path = corpus("first", "second")
    client = fake_client(
        topics=lambda prompt: (
            ["Supply Chain"] if "Meeting 0" in prompt else ["Supply Chain Risk"]
        ),
        merges=[TopicMerge(keep="Supply Chain", merge=["Supply Chain Risk"])],
    )

    assert run(["--db", str(path)], client) == 0

    assert "merged Supply Chain Risk into Supply Chain" in capsys.readouterr().out


def test_dedupe_can_be_skipped(corpus, fake_client, run, capsys):
    path = corpus("first")
    client = fake_client()

    assert run(["--db", str(path), "--no-dedupe"], client) == 0

    assert "duplicates" not in capsys.readouterr().out
    assert client.prompts(TopicMerges) == []


def test_a_failed_dedupe_does_not_undo_the_enrichment(corpus, fake_client, run, capsys):
    path = corpus("first")
    client = fake_client(merges=[TopicMerge(keep="Nonexistent", merge=["Firmware"])])

    assert run(["--db", str(path)], client) == 0

    assert summaries(path)["first"]
    assert "the dedupe pass failed" in capsys.readouterr().err


def test_a_failed_document_is_reported_and_the_run_fails(
    corpus, fake_client, run, capsys
):
    path = corpus("first", "second")

    def fail_the_first(prompt, text_format):
        if "Meeting 0" in prompt and text_format is DocumentSummary:
            return None
        return canned()(prompt, text_format)

    assert run(["--db", str(path)], fake_client(fail_the_first)) == 1

    captured = capsys.readouterr()
    assert "error: first:" in captured.err
    assert "Enriched 1 of 2 documents" in captured.out
    assert summaries(path)["second"]


def test_a_missing_store_is_reported_rather_than_created(
    tmp_path, fake_client, run, capsys
):
    path = tmp_path / "absent.db"

    assert run(["--db", str(path)], fake_client()) == 1

    assert "there is no document store" in capsys.readouterr().err
    assert not path.exists()


def test_a_missing_seed_list_stops_the_run_before_anything_is_called(
    corpus, fake_client, run, capsys, tmp_path
):
    path = corpus("first")
    client = fake_client()

    assert (
        run(["--db", str(path), "--topics", str(tmp_path / "absent.md")], client) == 1
    )

    assert client.calls == []
    assert "Could not read the seed categories" in capsys.readouterr().err


def test_a_missing_embedder_stops_the_run_before_any_billed_call(
    corpus, fake_client, capsys
):
    path = corpus("first")
    client = fake_client()

    def no_models():
        raise EnrichmentError("The embedding model is not installed. Run `uv sync`.")

    code = main(
        ["--db", str(path)],
        client_factory=lambda env: client,
        embedder_factory=no_models,
    )

    assert code == 1
    assert client.calls == []
    assert "embedding model is not installed" in capsys.readouterr().err


def test_embeddings_can_be_recomputed_on_request(corpus, fake_client):
    path = corpus("first")
    main(
        ["--db", str(path)],
        client_factory=lambda env: fake_client(),
        embedder_factory=lambda: (
            lambda texts: np.zeros((len(texts), 3), dtype=np.float32),
            "first-embedder",
        ),
    )

    main(
        ["--db", str(path), "--recompute-embeddings", "first"],
        client_factory=lambda env: fake_client(),
        embedder_factory=lambda: (
            lambda texts: np.ones((len(texts), 4), dtype=np.float32),
            "second-embedder",
        ),
    )

    connection = connect(path)
    try:
        models = {
            row["embedding_model"]
            for row in connection.execute("SELECT embedding_model FROM chunks")
        }
    finally:
        connection.close()
    assert models == {"second-embedder"}


def test_the_defaults_are_the_committed_paths():
    args = parse_args([])

    assert args.db.name == "corpus.db"
    assert args.topics.name == "topics.md"
    assert args.model


def test_the_client_is_built_from_the_environment(monkeypatch):
    built = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setattr("scripts.enrich.OpenAI", FakeOpenAI)

    build_client(
        {
            "OPENAI_API_KEY": "key",
            "OPENAI_BASE_URL": "https://example.invalid",
            "OPENAI_PROJECT": "project",
        }
    )

    assert built == {
        "api_key": "key",
        "base_url": "https://example.invalid",
        "project": "project",
    }


def test_a_missing_model_extra_is_named_with_the_command_that_fixes_it(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "corpus_query.models.embedder":
            raise ImportError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)

    with pytest.raises(EnrichmentError, match="uv sync --extra models"):
        build_embedder()


def test_a_store_written_by_another_version_is_refused(
    tmp_path, fake_client, run, capsys
):
    path = tmp_path / "corpus.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE something (id INTEGER PRIMARY KEY)")
    connection.execute("PRAGMA user_version = 99")
    connection.commit()
    connection.close()

    assert run(["--db", str(path)], fake_client()) == 1

    assert "schema version 99" in capsys.readouterr().err
