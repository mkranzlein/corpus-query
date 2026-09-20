You are writing three Word documents for Widget Makers Incorporated, a
ten-person hardware startup that designs and manufactures industrial sensors.
They are internal documents from the working life of a real company: a test
report, a readiness assessment, and a plan. Somebody at the company sat down
and wrote each one.

Write all three with the `docx` skill from the `document-skills` plugin. This
run produces these three `.docx` files and nothing else — no PowerPoint, no
Excel, no summary of what you did.

## Read these first

- `data/roster.md` — the cast. Every person named in any of the three
  documents is a first name from this file, spelled exactly as it appears.
  Invent nobody. Customers, suppliers, competitors, and product names may be
  invented freely.
- `data/topics.md` — the categories the corpus is filed under. Useful for
  knowing what this company's concerns are. Do not put the category names in
  the documents.
- `data/office_files_guidance.md` — what all nine office documents are, and
  how these three relate to the meeting transcripts. Read the whole file, not
  only the Word rows: the relationships and the planted imperfections are
  decided across all nine.

## What to write

Write these three, to `data/office/`:

| File | Author | Date | What it is |
| --- | --- | --- | --- |
| `xt-9-rev-b-thermal-qualification-report.docx` | Sofia | 2026-03-12 | Qualification report on thermal drift in the XT-9 Rev B, after the firmware workaround was tested. Scope, method, results per test chamber, findings, recommendation. |
| `iec-62443-certification-readiness-assessment.docx` | Callum | 2026-03-02 | Where the company stands against IEC 62443 and what closing the gap costs. Regulatory scope, gap analysis by requirement family, remediation plan, timeline and cost. |
| `contract-manufacturer-transition-plan.docx` | Devon | 2026-04-15 | Moving board assembly to a second contract manufacturer. Current state, candidate evaluation, transition phases, risks. |

## Authorship

Each document has exactly one author, set in the file's core properties. Put
the author's first name in both `author` and `last_modified_by`, and the
document's date in `created` and `modified`. No document has a second author,
a reviewer named in the properties, or a contributors list.

The author is the person whose job it is: the firmware engineer writes the
firmware test report, the general counsel writes the compliance assessment,
the manufacturing engineer writes the manufacturing plan. Other people are
named inside the text where it makes sense — someone ran a test, someone owns
an action — but they did not write it.

## Structure

The heading structure is what a citation will point at, so it has to be real.

- Every document uses `Heading 1` and `Heading 2`, and at least one uses
  `Heading 3`. Use the real Word heading styles, not bold paragraphs that look
  like headings.
- Six to ten sections at the top level, most with subsections under them. A
  document whose whole body sits under one heading is a failure of this
  prompt.
- Each of the deepest sections carries roughly 100 to 400 words. Vary it: some
  are two paragraphs, one or two are a single dense paragraph, and at least
  one across the three runs long enough that a reader would skim it.
- Headings say what the section is about — `Thermal Chamber Results` rather
  than `Results`, `Supplier Qualification Risk` rather than `Risks`. A
  heading path is what a reader is shown to explain where a quote came from,
  so `Test Results > Chamber B, 60 °C Soak` earns its place and
  `Section 3 > Part 2` does not.

Tables and bulleted lists are welcome where the content is genuinely tabular
or genuinely a list. Most of the body is prose.

## How it should read

Written, not spoken. These are not transcripts: complete paragraphs, a
consistent voice within each document, and the register of someone writing for
colleagues who will read it without them in the room.

The three do not read alike. A test report is precise and a little dry, and
states numbers plainly. A readiness assessment hedges where the answer is
genuinely unsettled and is careful about what it commits to. A transition plan
is written to be argued with — it has options, a recommendation, and things
that could go wrong.

Say concrete things. Give real figures: temperatures, drift in millivolts,
yields, per-unit costs, dates, week counts, named suppliers. A document that
says a result was "acceptable" without saying what it was gives retrieval
nothing to return and a reader nothing to check.

## What not to do

- **Do not cite meetings.** These documents cover subject matter that meeting
  transcripts also cover, and they use the same figures, but they never say
  "as discussed last week" or name a meeting. Each document stands alone as
  though it is the only record of its subject.
- **Do not write a cover page, a table of contents, a revision history, a
  distribution list, or a confidentiality banner.** They add no retrievable
  content and would chunk as noise.
- **Do not sign the document, date it in the body, or name yourself as the
  author inside the text.** The author lives in the file properties.
- **Do not mention that these are generated**, or refer to a corpus, a
  prompt, a skill, or a test.

## Imperfections

`data/office_files_guidance.md` lists three imperfections planted across all
nine office documents. Two are yours to place here. Plant them without drawing
attention to them, and without any document acknowledging that anything is
off:

1. One of these three states a figure that a later-dated document elsewhere
   in the corpus would state differently. Write it as the document's author
   would have: correct as far as they knew on the day.
2. The three are unevenly thorough. One is noticeably thinner than the other
   two — sections that are a paragraph where they should be a page, a section
   that promises detail and does not deliver it. Nothing marks it as
   incomplete.

Write the three files, nothing else. No commentary, no notes about what you
planted, no meta-text of any kind.
