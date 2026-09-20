"""Tests for pointing HF_HOME inside the project, and for trusting its cache.

Nothing here downloads or contacts the hub: cache state is controlled by
monkeypatching ``try_to_load_from_cache`` rather than touching an actual
Hugging Face cache.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from corpus_query.models.hf_home import (
    WEIGHTS_FILE,
    ensure_hf_home,
    is_cached,
    prefer_offline,
)


def test_sets_hf_home_when_unset(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HF_HOME", raising=False)
    target = tmp_path / "hf-cache"

    resolved = ensure_hf_home(target)

    assert resolved == target.resolve()
    assert resolved.is_dir()


def test_leaves_an_existing_hf_home_alone(tmp_path: Path, monkeypatch):
    already_set = tmp_path / "elsewhere"
    already_set.mkdir()
    monkeypatch.setenv("HF_HOME", str(already_set))

    resolved = ensure_hf_home(tmp_path / "unused")

    assert resolved == already_set


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


def test_is_cached_reflects_try_to_load_from_cache(cache_state):
    cache_state.add("repo/embedder")

    assert is_cached("repo/embedder", WEIGHTS_FILE) is True
    assert is_cached("repo/reranker", WEIGHTS_FILE) is False


def test_a_model_is_probed_for_its_weights_not_its_config(monkeypatch):
    """An interrupted download leaves the small files but not the weights.

    Probing anything but the weights would call that cache warm, when the
    model is not actually usable offline.
    """
    asked = []

    def half_downloaded(repo_id: str, filename: str):
        asked.append(filename)
        return None if filename == WEIGHTS_FILE else f"/fake/{repo_id}/{filename}"

    monkeypatch.setattr(
        "corpus_query.models.hf_home.try_to_load_from_cache", half_downloaded
    )

    assert is_cached("repo/embedder", WEIGHTS_FILE) is False
    assert asked == [WEIGHTS_FILE]


def test_prefer_offline_sets_the_flag_when_every_model_is_cached(
    cache_state, monkeypatch
):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    cache_state.update({"repo/embedder", "repo/reranker"})

    offline = prefer_offline(["repo/embedder", "repo/reranker"])

    assert offline is True
    assert os.environ.get("HF_HUB_OFFLINE") == "1"


def test_prefer_offline_leaves_the_flag_unset_on_a_cold_cache(cache_state, monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)

    offline = prefer_offline(["repo/embedder", "repo/reranker"])

    assert offline is False
    assert os.environ.get("HF_HUB_OFFLINE") is None


def test_prefer_offline_leaves_the_flag_unset_on_a_partial_cache(
    cache_state, monkeypatch
):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    cache_state.add("repo/embedder")

    offline = prefer_offline(["repo/embedder", "repo/reranker"])

    assert offline is False
    assert os.environ.get("HF_HUB_OFFLINE") is None


def test_prefer_offline_respects_an_explicit_opt_out(cache_state, monkeypatch):
    """An ``HF_HUB_OFFLINE=0`` already set stays authoritative.

    ``setdefault`` never overwrites it, whether or not the cache is warm
    enough that this call would otherwise have set it itself.
    """
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    cache_state.update({"repo/embedder", "repo/reranker"})

    offline = prefer_offline(["repo/embedder", "repo/reranker"])

    assert offline is False
    assert os.environ.get("HF_HUB_OFFLINE") == "0"


def test_prefer_offline_respects_an_explicit_opt_in_on_a_cold_cache(
    cache_state, monkeypatch
):
    """An ``HF_HUB_OFFLINE=1`` already set is reported even without a warm cache."""
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    offline = prefer_offline(["repo/embedder", "repo/reranker"])

    assert offline is True
    assert os.environ.get("HF_HUB_OFFLINE") == "1"
