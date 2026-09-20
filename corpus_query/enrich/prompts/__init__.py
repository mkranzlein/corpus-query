"""The enrichment prompts, one markdown file per pass.

A prompt is a file under version control, never a string inlined in the code
that sends it. It is the part most likely to be revised by hand, and a
markdown file is what someone revising it wants to open — and what a diff
reads well as.

Token substitution is :func:`corpus_query.transcripts.prompt.fill`, reused
rather than reimplemented: a prompt is prose that may grow braces of its own,
so ``{{token}}`` rather than :meth:`str.format` is a decision that should
hold across every prompt in the project, not just the generator's.
"""

from __future__ import annotations

from pathlib import Path

from corpus_query.transcripts.prompt import PromptError, fill

__all__ = ["PROMPT_DIR", "PromptError", "fill", "load", "render"]

#: Where the prompt files live: beside this module, inside the package, so
#: they are loaded through the package's own path rather than the cwd.
PROMPT_DIR = Path(__file__).parent

#: What a prompt file is called, given its pass name.
SUFFIX = ".md"


def load(name: str) -> str:
    """Read one prompt template.

    Args:
        name: The pass's name, such as ``summary``.

    Returns:
        The template text.

    Raises:
        PromptError: If the file cannot be read.
    """
    path = PROMPT_DIR / f"{name}{SUFFIX}"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptError(f"Could not read the prompt at {path}: {exc}") from exc


def render(name: str, values: dict[str, str]) -> str:
    """Read one prompt template and fill it in.

    Args:
        name: The pass's name, such as ``summary``.
        values: One entry per ``{{token}}`` the template uses.

    Returns:
        The prompt, ready to send.

    Raises:
        PromptError: If the template cannot be read, or does not match the
            values that fill it.
    """
    return fill(load(name), values)
