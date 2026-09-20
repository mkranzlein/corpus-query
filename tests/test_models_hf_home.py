"""Tests for pointing HF_HOME inside the project."""

from __future__ import annotations

from pathlib import Path

from corpus_query.models.hf_home import ensure_hf_home


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
