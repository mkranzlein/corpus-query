"""Deriving everything about a document that only a model can produce.

Ingestion is deterministic and free; enrichment is neither. Each pass here
sends a document to a model and writes what comes back: a summary, up to
five topics drawn from a shared category list, two priority fields, and an
embedding per chunk. The passes are separate modules because they fail
separately, and because a corpus is usually re-enriched one pass at a time.
"""
