"""The agent's prompts, one markdown file per prompt.

The same rule the enrichment prompts follow: a prompt is a file under version
control, never a string inlined in the code that sends it. It is the part
most likely to be revised by hand, and a markdown file is what someone
revising it wants to open — and what a diff reads well as.
"""

from __future__ import annotations

from pathlib import Path

from corpus_query.transcripts.prompt import PromptError

__all__ = ["PROMPT_DIR", "PromptError", "load"]

#: Where the prompt files live: beside this module, inside the package, so
#: they are loaded through the package's own path rather than the cwd.
PROMPT_DIR = Path(__file__).parent

#: What a prompt file is called, given its name.
SUFFIX = ".md"


def load(name: str) -> str:
    """Read one prompt.

    Args:
        name: The prompt's name, such as ``answer``.

    Returns:
        The prompt text.

    Raises:
        PromptError: If the file cannot be read.
    """
    path = PROMPT_DIR / f"{name}{SUFFIX}"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptError(f"Could not read the prompt at {path}: {exc}") from exc
