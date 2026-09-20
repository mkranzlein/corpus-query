"""Pre-fetch the embedding and reranking model weights.

``uv sync --extra models`` installs torch and sentence-transformers but
downloads no weights: ``BAAI/bge-small-en-v1.5`` (127 MB) and
``cross-encoder/ms-marco-MiniLM-L-6-v2`` (87 MB) are fetched lazily, the
first time something loads them. Left alone, that first fetch happens
inside ``uv run scripts/serve.py``, which stalls silently for around 215 MB
of downloads before it binds a socket. This script does the same fetch, up
front, with output that says what is happening.

Both models load through the cached, idempotent loaders in
:mod:`corpus_query.models`, and :func:`corpus_query.models.hf_home.
ensure_hf_home` already points the cache at the gitignored
``.cache/huggingface/`` inside the project, so this script is a thin front
end over what startup does anyway. Startup still warms the models itself —
this only front-loads the download, so that step is not a surprise the
first time someone runs the service.

Run it with::

    uv sync --extra models          # once: torch, sentence-transformers
    uv run scripts/fetch_models.py

Nothing here calls a hosted model and nothing costs anything: both
downloads are of public weights, over a plain HTTPS GET.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from corpus_query.models.hf_home import WEIGHTS_FILE, ensure_hf_home, is_cached

ensure_hf_home()


@dataclass(frozen=True)
class ModelSpec:
    """One model to fetch: its identifier, its size, and how to load it."""

    repo_id: str
    size: str
    probe_file: str
    load: Callable[[], object]


def default_model_specs() -> list[ModelSpec]:
    """Build the list of models this project needs.

    Imported inside the function, not at module level, because importing
    either loader pulls in torch, which is an optional extra. Deferring the
    import is what lets a missing extra be reported as one line instead of
    an import traceback.

    Returns:
        The embedder and the reranker, in the order they should be fetched.

    Raises:
        ImportError: If the models extra is not installed.
    """
    from corpus_query.models.embedder import EMBEDDING_MODEL_ID, load_embedder
    from corpus_query.models.reranker import RERANKER_MODEL_ID, load_reranker

    return [
        ModelSpec(EMBEDDING_MODEL_ID, "127 MB", WEIGHTS_FILE, load_embedder),
        ModelSpec(RERANKER_MODEL_ID, "87 MB", WEIGHTS_FILE, load_reranker),
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Arguments to parse. Defaults to the process arguments.

    Returns:
        The parsed arguments. There is nothing to configure; parsing exists
        so ``--help`` works and a stray argument is reported.
    """
    parser = argparse.ArgumentParser(
        description="Pre-fetch the embedding and reranking model weights."
    )
    return parser.parse_args(argv)


def fetch_models(specs: Sequence[ModelSpec], cache_dir: Path, out=None) -> None:
    """Fetch every model that is not already cached.

    Args:
        specs: The models to make sure are cached.
        cache_dir: Where the cache lives, printed at the end so a caller
            knows where the weights landed.
        out: Where to print progress. Defaults to ``sys.stdout``, resolved
            at call time so a test can capture it. Overridable in tests.
    """
    out = out if out is not None else sys.stdout
    for spec in specs:
        if is_cached(spec.repo_id, spec.probe_file):
            print(f"{spec.repo_id} is already cached, nothing to fetch.", file=out)
            continue
        print(f"Fetching {spec.repo_id} ({spec.size})...", file=out)
        spec.load()

    print(f"Model cache: {cache_dir}", file=out)


def main(
    argv: list[str] | None = None,
    model_specs: Callable[[], list[ModelSpec]] = default_model_specs,
) -> int:
    """Run the script.

    Args:
        argv: Command-line arguments. Defaults to the process arguments.
        model_specs: What to fetch. Overridable in tests so nothing real
            downloads.

    Returns:
        A process exit code. Non-zero if the models extra is not installed.
    """
    parse_args(argv)
    cache_dir = ensure_hf_home()

    try:
        specs = model_specs()
    except ImportError as exc:
        print(
            f"error: the embedding and reranking models are not installed "
            f"({exc}). Run `uv sync --extra models` and try again.",
            file=sys.stderr,
        )
        return 1

    fetch_models(specs, cache_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
