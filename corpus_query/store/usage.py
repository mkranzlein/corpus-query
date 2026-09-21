"""Where the record of the system being used lives.

Two SQLite files, and the split between them is about who writes to them.

The document store is the corpus: written once by ingestion and enrichment,
committed to the repository so a clone can query without building anything,
and read-only in normal use. The usage database is everything the running
service produces about itself — graph checkpoints today, and the captured
records and telemetry later work will add — which is per-installation, grows
with use, and is worth nothing to anyone else.

Keeping them apart is what lets the corpus stay a committed artifact. Sharing
one file would mean that asking a question modifies a checked-in binary, so
``git status`` would go dirty on a clone whose only crime was running the
thing, and every pull would be a conflict on a file nobody edited.

Nothing here creates a schema. SQLite makes the file on first connection and
each writer owns its own tables in it; this module's job is only to say where
the file is and to make sure the directory beneath it exists.
"""

from __future__ import annotations

from pathlib import Path

#: Where the usage database lives by default, relative to the repository
#: root. Beside the corpus, and ignored by git for the reasons above.
DEFAULT_USAGE_DATABASE_FILE = Path("data/usage.db")


def usage_database(path: Path | str | None = None) -> Path:
    """Resolve where the usage database lives, ready to be opened.

    The default is read here, on each call, rather than bound into a
    caller's default argument. A default argument is evaluated when its
    module is imported, which would make the constant above unpatchable
    afterwards — and the test suite patches it, so that a test which
    forgets to stub the agent writes to a temporary file instead of into
    the repository.

    SQLite creates the file itself but not the directory holding it, and a
    fresh clone should not need a setup step before it can answer a
    question, so the directory is created here.

    Args:
        path: Where the usage database should live, or None for the
            project's default.

    Returns:
        The path, with its parent directory in place.
    """
    resolved = Path(DEFAULT_USAGE_DATABASE_FILE if path is None else path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
