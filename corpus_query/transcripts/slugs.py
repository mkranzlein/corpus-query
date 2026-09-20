"""Turning a meeting subject into a filename.

A slug is how a meeting is named on disk and how a document is identified
afterwards, so it has to be derived the same way every time and has to stay
unique. Two meetings may reasonably share a subject — a company that holds a
"Weekly manufacturing sync" holds it more than once — so a collision takes a
numeric suffix instead of overwriting what is already there.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: What a slug is allowed to be made of, once everything else is stripped.
_KEEP = re.compile(r"[^a-z0-9]+")

#: Used when a subject has no usable characters at all, such as one written
#: entirely in punctuation.
FALLBACK_SLUG = "meeting"


def slugify(subject: str) -> str:
    """Derive a slug from a meeting subject.

    Args:
        subject: The meeting's subject.

    Returns:
        The subject lowercased, with every run of anything that is not a
        letter or a digit replaced by a hyphen, and the ends trimmed.
    """
    return _KEEP.sub("-", subject.lower()).strip("-") or FALLBACK_SLUG


def unique_slug(subject: str, taken: Iterable[str]) -> str:
    """Derive a slug that nothing else is using.

    Args:
        subject: The meeting's subject.
        taken: Slugs already spoken for, on disk or earlier in this batch.

    Returns:
        The slug, with ``-2``, ``-3``, and so on appended until it is free.
    """
    slug = slugify(subject)
    spoken_for = set(taken)
    if slug not in spoken_for:
        return slug
    suffix = 2
    while f"{slug}-{suffix}" in spoken_for:
        suffix += 1
    return f"{slug}-{suffix}"
