"""The kinds a document and a chunk can be.

Two vocabularies live here. ``source_kind`` says what a document was read
out of — a rendered transcript, a Word document, a deck, a workbook — and
``chunks.kind`` says how a span of it was cut. Both are CHECK constrained in
the schema, so a typo is rejected by the database rather than filed under a
kind nothing queries.

The schema is the enforcement; these constants are what the Python side
writes and reads, and a test asserts the two lists agree. They are kept in
one module rather than next to the code that produces each kind, because a
reader for a new format has to pick names from a list that already exists,
not add a third place where kinds are spelled out.

Only the transcript kinds are produced today. The rest are named here, and
permitted by the schema, so that adding a parser for a format is a reader and
a chunker rather than a schema change under a corpus that is already stored.
"""

from __future__ import annotations

#: A rendered meeting transcript. Its people are ``attendees`` rows rather
#: than an author, because a meeting has no single one.
TRANSCRIPT = "transcript"

#: A Word document, a PowerPoint deck, and an Excel workbook. Each has one
#: author, recorded in ``documents.author``.
DOCX = "docx"
PPTX = "pptx"
XLSX = "xlsx"

#: Every kind a document may claim, in the order the formats were added.
SOURCE_KINDS = (TRANSCRIPT, DOCX, PPTX, XLSX)

#: A window of whole turns from a transcript. Its span is turn indices.
TURN_WINDOW = "turn_window"

#: A heading section of a Word document. Its span is paragraph indices.
DOCX_SECTION = "docx_section"

#: One slide, its body and its notes together. Its span is the slide number,
#: start and end alike: a slide is a span of one.
SLIDE = "slide"

#: A window of spreadsheet rows, rendered as a table. Its span is row
#: numbers.
ROW_WINDOW = "row_window"

#: The two kinds written about something rather than taken from a span of
#: it: the document summary enrichment writes, and a description of one
#: sheet of a workbook. Neither carries a span.
SUMMARY = "summary"
SHEET_SUMMARY = "sheet_summary"

#: The kinds whose chunks are spans of their document, and so carry
#: ``span_start`` and ``span_end``.
SPAN_CHUNK_KINDS = (TURN_WINDOW, DOCX_SECTION, SLIDE, ROW_WINDOW)

#: The kinds written about a document rather than cut out of it, which carry
#: no span at all.
SUMMARY_CHUNK_KINDS = (SUMMARY, SHEET_SUMMARY)

#: Every kind a chunk may claim.
CHUNK_KINDS = SPAN_CHUNK_KINDS + SUMMARY_CHUNK_KINDS
