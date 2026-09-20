"""The one error enrichment raises.

Every way a pass can fail — a response with no parsed output, a response
naming a category that does not exist, a document that is not in the store —
surfaces as this, so a caller enriching a corpus can catch one thing, report
it, and carry on with the next document.
"""

from __future__ import annotations


class EnrichmentError(Exception):
    """A document could not be enriched."""
