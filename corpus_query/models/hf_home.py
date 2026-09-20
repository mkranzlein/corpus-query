"""Keeping downloaded model weights inside the project, and off the network.

``huggingface_hub`` reads ``HF_HOME`` once, at import time, to decide where
its cache lives. Left unset, that default is a directory under the user's
home, so weights downloaded while running this project would pile up on
whoever's machine happens to run it first — a stray ~200MB nobody asked for
outside the repo.

:func:`ensure_hf_home` points it at a gitignored directory inside the
project instead. It has to run before anything imports
``huggingface_hub``, ``transformers``, or ``sentence_transformers``, which is
why :mod:`corpus_query.models.embedder` and
:mod:`corpus_query.models.reranker` call it before importing
``sentence_transformers`` themselves.

This module also owns whether that cache is trusted without asking the hub.
Loading a model normally revalidates every cached file against the hub even
when nothing has changed, which is wasted network on a warm cache.
:func:`prefer_offline` skips that revalidation once :func:`is_cached` says
there is nothing to revalidate against.

``huggingface_hub`` itself is a dependency of ``chromadb``, which is always
installed, so importing it here does not pull in the models extra —
unlike :mod:`corpus_query.models.embedder` and
:mod:`corpus_query.models.reranker`, which import ``sentence_transformers``
and therefore torch.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from huggingface_hub import try_to_load_from_cache

#: Relative to the repository root. Listed in .gitignore alongside the rest
#: of ``.cache/``.
DEFAULT_HF_HOME = Path(".cache") / "huggingface"

#: What a model is probed for to decide whether it is already cached. Both
#: models this project uses ship their weights under this name, and it is
#: the largest file in either repo — so it is the last to land and the one
#: worth asking about.
WEIGHTS_FILE = "model.safetensors"


def ensure_hf_home(path: Path | str = DEFAULT_HF_HOME) -> Path:
    """Point ``HF_HOME`` inside the project, unless already set.

    An ``HF_HOME`` already present in the environment is left alone, so a
    developer or CI job that wants a different cache location can still set
    one.

    Args:
        path: Where the cache should live, relative to the current working
            directory unless already absolute.

    Returns:
        The resolved cache directory now in effect, which exists on disk
        whether or not this call set it.
    """
    os.environ.setdefault("HF_HOME", str(Path(path).resolve()))
    resolved = Path(os.environ["HF_HOME"])
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def is_cached(repo_id: str, filename: str) -> bool:
    """Report whether a model is already in the local Hugging Face cache.

    The file to probe with is the weights rather than anything smaller.
    Config and tokenizer files are fetched first and are a few hundred bytes
    each, so a download interrupted part way leaves them on disk with the
    weights still missing. Probing one of those would call that cache warm
    when the model is not actually usable offline.

    Args:
        repo_id: The Hugging Face repo to check.
        filename: The file to look for, as a stand-in for the whole model
            being cached. See :data:`WEIGHTS_FILE`.

    Returns:
        True if the file is already on disk, meaning loading the model
        would not need the network.
    """
    return isinstance(try_to_load_from_cache(repo_id, filename), str)


def prefer_offline(repo_ids: Sequence[str]) -> bool:
    """Skip Hugging Face Hub revalidation when every model is already cached.

    Loading a model normally issues a HEAD request per cached file to check
    it against the hub's current tip, plus probes for optional configs that
    may not exist in the repo. None of that transfers any weights, but it
    still depends on the network and prints a warning about unauthenticated
    requests on the first one. ``HF_HUB_OFFLINE=1`` skips it entirely and
    loads straight from the cache — safe only when every file a load would
    need is already there, since offline mode turns a cache miss into a
    hard failure instead of falling back to a download.

    ``HF_HUB_OFFLINE`` is set with :func:`os.environ.setdefault`, matching
    how :func:`ensure_hf_home` treats ``HF_HOME``: a value already present in
    the environment — including an explicit ``"0"`` — is left alone, so a
    developer or CI job that wants the hub contacted regardless can still
    force that.

    Args:
        repo_ids: The models that are about to be loaded. Offline mode is
            only preferred when every one of them is cached; a single
            missing model means today's behavior — the network fills in
            whatever is missing.

    Returns:
        Whether ``HF_HUB_OFFLINE`` is set to ``"1"`` once this call
        returns, whether because it set that just now or because it was
        already set that way.
    """
    if all(is_cached(repo_id, WEIGHTS_FILE) for repo_id in repo_ids):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    return os.environ.get("HF_HUB_OFFLINE") == "1"
