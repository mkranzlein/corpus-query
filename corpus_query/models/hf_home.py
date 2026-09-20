"""Keeping downloaded model weights inside the project.

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
"""

from __future__ import annotations

import os
from pathlib import Path

#: Relative to the repository root. Listed in .gitignore alongside the rest
#: of ``.cache/``.
DEFAULT_HF_HOME = Path(".cache") / "huggingface"


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
