"""Tests for the model-prefetch entry point.

Nothing downloads: each model's ``load`` is a recorder instead of the real
loader, and cache state is controlled by monkeypatching
``try_to_load_from_cache`` rather than touching an actual Hugging Face
cache. ``WEIGHTS_FILE`` and ``is_cached`` live in
:mod:`corpus_query.models.hf_home`; this script just imports them, so their
own behavior is covered in ``tests/test_models_hf_home.py``.
"""

from __future__ import annotations

import pytest

from scripts.fetch_models import WEIGHTS_FILE, ModelSpec, main, parse_args


class _Recorder:
    """Stands in for a model loader, recording whether it was called."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


def _specs(cached: set[str]) -> tuple[list[ModelSpec], dict[str, _Recorder]]:
    """Build fake specs, with one loader per repo and a fixed cache state."""
    loaders = {"repo/embedder": _Recorder(), "repo/reranker": _Recorder()}
    specs = [
        ModelSpec("repo/embedder", "127 MB", WEIGHTS_FILE, loaders["repo/embedder"]),
        ModelSpec("repo/reranker", "87 MB", WEIGHTS_FILE, loaders["repo/reranker"]),
    ]
    return specs, loaders


@pytest.fixture
def cache_state(monkeypatch):
    """Control which repos ``is_cached`` reports as already warm."""
    cached: set[str] = set()

    def fake_try_to_load_from_cache(repo_id: str, filename: str):
        return f"/fake/{repo_id}/{filename}" if repo_id in cached else None

    monkeypatch.setattr(
        "corpus_query.models.hf_home.try_to_load_from_cache",
        fake_try_to_load_from_cache,
    )
    return cached


def test_a_cold_cache_fetches_every_model(cache_state, capsys):
    specs, loaders = _specs(cache_state)

    code = main([], model_specs=lambda: specs)

    assert code == 0
    assert loaders["repo/embedder"].calls == 1
    assert loaders["repo/reranker"].calls == 1
    out = capsys.readouterr().out
    assert "Fetching repo/embedder (127 MB)" in out
    assert "Fetching repo/reranker (87 MB)" in out


def test_a_warm_cache_downloads_nothing(cache_state, capsys):
    cache_state.update({"repo/embedder", "repo/reranker"})
    specs, loaders = _specs(cache_state)

    code = main([], model_specs=lambda: specs)

    assert code == 0
    assert loaders["repo/embedder"].calls == 0
    assert loaders["repo/reranker"].calls == 0
    out = capsys.readouterr().out
    assert "repo/embedder is already cached, nothing to fetch." in out
    assert "repo/reranker is already cached, nothing to fetch." in out


def test_a_partially_warm_cache_fetches_only_what_is_missing(cache_state, capsys):
    cache_state.add("repo/embedder")
    specs, loaders = _specs(cache_state)

    main([], model_specs=lambda: specs)

    assert loaders["repo/embedder"].calls == 0
    assert loaders["repo/reranker"].calls == 1


def test_reports_where_the_cache_lives(cache_state, capsys, monkeypatch, tmp_path):
    specs, _ = _specs(cache_state)
    monkeypatch.setattr(
        "scripts.fetch_models.ensure_hf_home", lambda: tmp_path / "hf-cache"
    )

    main([], model_specs=lambda: specs)

    assert str(tmp_path / "hf-cache") in capsys.readouterr().out


def test_a_missing_models_extra_is_reported_as_one_line(capsys):
    def missing_extra():
        raise ImportError("No module named 'sentence_transformers'")

    code = main([], model_specs=missing_extra)

    assert code == 1
    error = capsys.readouterr().err
    assert "uv sync --extra models" in error
    assert error.count("\n") == 1


def test_a_half_downloaded_model_is_fetched_again(monkeypatch, capsys):
    def half_downloaded(repo_id: str, filename: str):
        return None if filename == WEIGHTS_FILE else f"/fake/{repo_id}/{filename}"

    monkeypatch.setattr(
        "corpus_query.models.hf_home.try_to_load_from_cache", half_downloaded
    )
    specs, loaders = _specs(set())

    code = main([], model_specs=lambda: specs)

    assert code == 0
    assert loaders["repo/embedder"].calls == 1
    assert loaders["repo/reranker"].calls == 1
    assert "already cached" not in capsys.readouterr().out


def test_parse_args_takes_no_arguments():
    args = parse_args([])

    assert vars(args) == {}


def test_parse_args_rejects_a_stray_argument():
    with pytest.raises(SystemExit):
        parse_args(["--nope"])
