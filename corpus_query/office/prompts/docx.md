You are writing three Word documents for Main St Widget Foundry LLC, a
ten-person hardware startup that designs and makes widgets, gizmos, and
gadgets. They are internal documents from the working life of a real company: a
test report, a readiness assessment, and a plan. Somebody at the company sat
down and wrote each one.

What the products are is deliberately left vague. They are physical hardware —
circuit boards, enclosures, firmware — built in volume and sold to business
customers, and they go by model names. Nothing written about them says what one
measures, controls, or is for: they come up in terms of revisions, costs,
yields, defects, and prices. "Foundry" is only part of the company's name. It
does no metal casting, and nothing in a document should suggest that it does.

Write all three with the `docx` skill from the `document-skills` plugin. This
run produces these three `.docx` files and nothing else — no PowerPoint, no
Excel, no summary of what you did.

## Read these first

- `data/roster.md` — the cast. Every person named in any of the three
  documents is a first name from this file, spelled exactly as it appears.
  Invent nobody. Customers, suppliers, competitors, and product names are
  invented — never borrowed from a real company, product, or brand, and
  never a name you recognize as belonging to one.
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
| `mx-3-firmware-2-4-2-soak-test-report.docx` | Sofia | 2026-04-14 | Test report on MX-3 firmware 2.4.2, the fix for the idle-period watchdog fault, after the patch was soak tested. Scope, method, results per test rig, findings, release recommendation. |
| `ce-marking-readiness-assessment.docx` | Callum | 2026-02-24 | Where the company stands against CE marking for the GX-7 and RV-2 and what closing the gap costs. Directives in scope, gap analysis, RoHS documentation, test lab plan, timeline and cost. |
| `end-of-line-test-station-upgrade-plan.docx` | Devon | 2026-02-26 | Replacing the end-of-line functional test stations at the contract manufacturer. Current state, options evaluated, rollout phases, risks. |

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
- Headings say what the section is about — `Idle Soak Results` rather than
  `Results`, `Supplier Qualification Risk` rather than `Risks`. A heading
  path is what a reader is shown to explain where a quote came from, so
  `Test Results > Rig B, 72-Hour Idle Soak` earns its place and
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

Say concrete things. Give real figures: soak hours, fault counts, yields,
per-unit costs, dates, week counts, named suppliers. A document that
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
nine office documents. One is yours to place here. Plant it without drawing
attention to it, and without any document acknowledging that anything is
off:

The three are unevenly thorough. One is noticeably thinner than the other
two — sections that are a paragraph where they should be a page, a section
that promises detail and does not deliver it. Nothing marks it as
incomplete.

Write the three files, nothing else. No commentary, no notes about what you
planted, no meta-text of any kind.
