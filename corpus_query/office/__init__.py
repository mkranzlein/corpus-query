"""Office documents: Word, PowerPoint, and Excel.

Transcripts are the corpus's first format but not its only one. The readers
and chunkers for the office formats live here, one module per format, behind
the same reader interface ingestion dispatches to for a transcript.

Only the generation prompts are here so far. The files they produce are
committed to ``data/office/``.
"""
