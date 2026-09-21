# Planted imperfections

The meeting corpus is deliberately imperfect. A corpus in which every document
agrees with every other, every question is answered, and every transcript is
equally well recorded would make retrieval look better than it is: the
interesting failures — a confident answer drawn from a stale document, a
question the corpus cannot settle — would never come up.

So the generator asks for specific flaws. This file records which ones, and
where they ended up, so the corpus's intended failure modes are documented
rather than folklore.

## What the generator asks for

Each batch is asked to plant all four of these. The prompt is in
`corpus_query/transcripts/prompt.md`.

1. **Contradictory facts.** Two meetings state something incompatible about the
   same thing — a unit cost, a ship date, a test yield, a headcount. Neither
   acknowledges the other.
2. **An unanswered question.** Someone asks a direct question that nobody
   answers. It does not become an action item; the conversation simply moves
   on.
3. **A reversed decision.** A decision made in an earlier-dated meeting is
   reached the opposite way in a later-dated one. Because meetings are
   independent snapshots with no cross-references, the later meeting does not
   mention the earlier one — it decides differently as though for the first
   time.
4. **Uneven transcript quality.** Some meetings read crisply; others ramble,
   trail off, or land mid-thought. Nothing marks the difference.

## What was planted

The corpus is generated in batches, so this section is appended to after each
run: read the batch, find the four, and record them here. Record enough to
find it again — the slugs involved and the fact in dispute — but not so much
that this file becomes a second copy of the corpus.

Asking for an imperfection is not the same as getting one. Two of the four
landed, one landed in a weaker form than it was asked for, and one did not
land at all. That is recorded below rather than quietly omitted, because a
list of intended flaws that is really a list of requested flaws would be
worse than no list: it would have us testing against failures the corpus does
not actually contain.

### Batch 1 — ten meetings, 2026-01-14 to 2026-06-02

| Imperfection | Meetings | What it is |
| --- | --- | --- |
| Reversed decision — **landed** | `xt-9-rev-b-thermal-drift-firmware-workaround-feasibility` (2026-03-05) → `customer-escalation-brannock-refinery-account` (2026-04-08) | March decides to build a firmware thermal-compensation update for Rev B units and ship it to the field, with Sofia on it as her primary focus and a draft due March 19th. In April, Marcus tells the same problem's escalation that the fix "is a component change on the output stage, it's not something you can patch in firmware." Neither the decision nor Sofia's in-flight work is mentioned. |
| Contradictory facts — **weaker than asked for** | `xt-9-rev-b-thermal-drift-firmware-workaround-feasibility` (2026-03-05) → `customer-escalation-brannock-refinery-account` (2026-04-08) | Not the incompatible figure the prompt asks for. What landed is a contradiction about what is known: in March, Marcus gives the Rev B field population as "somewhere around 340 units." In April, asked the same question, he says he does not have the number and that producing it would mean cross-referencing the shipping manifest against the hardware revision log — "not a five-minute job." No figure in the corpus contradicts another figure. |
| Unanswered question — **did not land** | — | Every direct question in all ten meetings draws a reply in the very next turn. The nearest approximations are questions deflected rather than dropped: Jamal asking how many Rev B units are in the field (2026-04-08) and Renata asking the total SLA credit exposure (2026-06-02) both get "I don't have that" and then become action items, which is the opposite of the conversation moving on. |
| Uneven quality — **weakly** | Most uneven: `support-backlog-and-ticket-sla-review`, `q1-sales-pipeline-review`. Most polished: `sensor-unit-cost-review-proximasense-x4`, `fieldsense-200-series-volume-pricing-authorization` | There is a measurable spread — self-interruptions and hedges cluster in two transcripts and are nearly absent from two others, and the Brannock escalation carries a garbled idiom ("caught off-blind") of the kind a transcription pass leaves behind. But no transcript is hard to follow, and none rambles or lands mid-thought the way the prompt asks for. All ten are legible throughout. |

### What this means for the corpus

The failure the corpus does test well is the stale document: the Rev B thermal
arc runs across two meetings that disagree about both the fix and what is
known, with no cross-reference between them for retrieval to lean on. A
question about how the Rev B drift is being addressed has two defensible
answers a month apart, and nothing in either meeting flags the other.

The failure it does not test is the unanswerable question. Every question here
has an answer somewhere in the same meeting, so a corpus-wide "nothing here
settles this" cannot be provoked from the transcripts alone. Worth knowing
before treating an abstention test as passing on the strength of this corpus.

The office documents in `data/office_files_guidance.md` plant their own three,
one of which — a figure that disagrees between a workbook and a deck — was
meant to be the numeric contradiction this batch did not produce. It landed:
see the office documents section below.

## Office documents

Nine office documents — three Word documents, three PowerPoint decks, three
Excel workbooks — sit alongside the transcripts under `data/office/`.
`data/office_files_guidance.md` asked the generator for three imperfections
across the nine: a document contradicted by a later meeting, a number that
appears in a workbook and a deck and disagrees, and uneven depth. It also
asked that documents never cite meetings, so any contradiction across formats
has to be found by comparing figures directly, the way retrieval would.

This section reads the nine committed files and records what actually landed,
the same way batch 1 of the transcripts is recorded above. All three asks
landed, one of them only within one of the two formats it could have spanned.
A fourth contradiction, not asked for, turned up between two of the documents
and is recorded alongside them, since retrieval will run into it regardless
of whether it was planted on purpose.

### What was planted

| Imperfection | Documents | What it is |
| --- | --- | --- |
| Document contradicted by a later meeting — **landed** | `xt-9-rev-b-thermal-qualification-report.docx` (Sofia, 2026-03-12) → `customer-escalation-brannock-refinery-account` (2026-04-08) | The qualification report's Recommendation section ("Field Release of the Compensation Firmware") recommends releasing firmware 3.5.0 with thermal compensation enabled by default to all Rev B units in the field, having tested it into the −40 °C to 55 °C range. In the later transcript, Elena asks Marcus directly whether the Rev B thermal drift is a firmware or hardware issue, and Marcus answers "the fix is a component change on the output stage, it's not something you can patch in firmware" — with no qualification that firmware helps for part of the population, the way the report found. `brannock-refinery-account-recovery-briefing.pptx` (Elena, 2026-04-14, slide 5, "Root Cause: Rev B Analog Output Drift") repeats the same hardware-only framing ("Cannot be corrected in firmware") for a specific account, again without reference to the report's tested mitigation. |
| A number that appears in a workbook and a deck and disagrees — **landed** | `q1-sales-pipeline.xlsx` (Jamal, 2026-03-30) → `q1-board-review.pptx` (Priya, 2026-04-02) | Slide 6, "Q2 Pipeline by Stage," names three opportunities with figures that do not match the `Open Opportunities` sheet they are drawn from. Tallis Water Authority: the sheet gives $232,000 at the Proposal stage (row 3, `Open Opportunities!F3`); the slide gives $112,000 under a "Commit" bucket. Thornbury Power: the sheet gives $104,000 at Proposal (row 4, `F4`); the slide gives $196,000 under "Negotiation." Sable Creek Gas: the sheet gives $174,000 at Discovery (row 9, `F9`); the slide gives $140,000, also under "Negotiation." The totals disagree as well: the workbook's own `Q2 Forecast by Month` sheet states $2,100,000 total open pipeline and $881,000 weighted (`C5`, `D5`); summing the `Open Opportunities` amounts directly gives $2,555,110, weighted $926,511 by win probability. The slide states $2.12M total and $1.26M weighted. No two of the three totals agree, and the weighted figure the slide uses is 40% higher than either figure the workbook itself supports. |
| Uneven depth — **landed, among the three Word documents** | `iec-62443-certification-readiness-assessment.docx` (Callum, 1,098 words) vs. `xt-9-rev-b-thermal-qualification-report.docx` (Sofia, 2,738 words) and `contract-manufacturer-transition-plan.docx` (Devon, 3,128 words) | The certification assessment covers the same kind of ground as its two siblings — a gap analysis, a remediation plan, a cost estimate — in under half the length of either, and thinly: its "Gap Analysis by Requirement Family" gives each gap one or two sentences, where the qualification report tabulates results at every soak point and the transition plan scores three candidate manufacturers against six weighted criteria. The three decks (14, 15, and 17 slides, each with a comparable level of speaker-note detail) and three workbooks show no equivalent spread — the unevenness is confined to the Word documents. |

### An unasked-for contradiction between two documents

`iec-62443-certification-readiness-assessment.docx` (Callum, 2026-03-02) tables
three preliminary assessment-body quotes under "Assessment Body Selection":
Kestrel Conformity Services at $86,000, Arden Certification GmbH at $104,000,
and Lindqvist Assurance at $118,000. `q1-board-review.pptx` (Priya,
2026-04-02, slide 16, "IEC 62443: Meridian's Q3 Requirement") states the range
as "$92–118K." The high end matches Lindqvist's quote; the low end matches
none of the three figures in the document it is drawn from. This was not
among the three imperfections the guidance file asked for.

### What this means for the corpus

The workbook-versus-deck contradiction the transcript batch did not produce
is present here, and more thoroughly than a single figure: three named
opportunities and two different pipeline totals disagree between the sales
pipeline workbook and the board deck built from it, giving retrieval several
independent ways to return a wrong number with an authoritative-looking
source. The document-versus-meeting failure mode is also confirmed outside
the transcripts — a written recommendation, tested and dated, contradicted a
month later by people who don't cite it, which is exactly the stale-document
risk the corpus is meant to test.

What did not fully land is the clean three-way split the guidance implied: no
single document is uniformly thin, and no deck or workbook shows the same
spread the Word documents do. A reader testing "does retrieval notice when
one source is far less detailed than another" gets a real case, but only
within one of the three formats.
