# Building a corpus

The corpus in this repository has already been built, and nothing below needs
running to use it. This is how it got there, and what to run if you want a
corpus of your own instead.

```bash
uv run scripts/generate_transcripts.py   # billed; --dry-run prints the prompt
uv run scripts/ingest.py                 # free, offline, deterministic
uv run scripts/enrich.py                 # billed; --dry-run prints the prompts
```

Ingestion reads each document with the reader for its format — a transcript is
split into chunks of whole turns, a Word document into its heading sections, a
deck into one chunk per slide, and a workbook into windows of 10 to 20 rows per
sheet, each rendered as a markdown table with its header repeated — so a
citation can say which section, slide, or row range a claim came from — and
writes documents, attendees, and chunks. With no paths named it reads both
`data/transcripts` and `data/office`. Enrichment adds a summary, topics, a time
sensitivity, a business
impact, and an embedding per chunk. Querying reads what those three leave
behind and calls nothing.

The two billed steps need a Bedrock key; see
[docs/provisioning.md](provisioning.md) for where one comes from and how
the spend is bounded.

A `.doc`, `.ppt`, or `.xls` file is converted to its modern equivalent with
LibreOffice headless before it is read, so the corpus never needs a separate
reader for the legacy binary formats. LibreOffice is optional: the committed
corpus is all modern files, needs none of it, and nothing here requires it to
be installed. It only matters if a legacy file is added to the corpus later,
in which case ingesting it needs LibreOffice on `PATH` or, on macOS, in the
usual place the app installs it.

The Word, PowerPoint, and Excel files in `data/office/` were written by a
Claude Code session running Opus, after the transcripts existed, working from
one prompt per file type:
[docx.md](../corpus_query/office/prompts/docx.md),
[pptx.md](../corpus_query/office/prompts/pptx.md), and
[xlsx.md](../corpus_query/office/prompts/xlsx.md). The prompts build on
[data/office_files_guidance.md](../data/office_files_guidance.md), which specifies
the nine documents and how each relates to the meetings.

Every invented name in the corpus — customers, suppliers, competitors, and
products — was checked with a web search after it was generated, and any that
turned out to belong to a real company or product was replaced. In the
transcripts the replacement was made in the JSON, and the markdown was
re-rendered from it with the renderer the generator uses, so the two still
agree.
