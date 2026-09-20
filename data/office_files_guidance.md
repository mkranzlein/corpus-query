# Office files guidance

Nine office documents belong to this corpus alongside the meeting
transcripts: three Word documents, three PowerPoint decks, and three Excel
workbooks. This file settles all nine in one place — what each one is, who
wrote it, and when — so that the three generation prompts can each name their
own three without the nine drifting into each other.

It is committed for the same reason `roster.md` and `topics.md` are. Subjects
chosen three at a time have no way to balance against the other six: three
decks and three memos can easily cover the same ground, or cover ground the
transcripts never touch. Deciding all nine at once is what stops that, and
keeping the decision in one file means reshuffling one document later is one
edit rather than three prompts falling out of step.

The cast is `roster.md` and the seed categories are `topics.md`. Neither is
restated here.

## What every document has

- **One author.** A first name from `roster.md`, set in the file's core
  properties, and the same name in both `author` and `last_modified_by`. This
  is the difference that matters between an office document and a transcript:
  a transcript has attendees and no author, an office document has an author
  and no attendees.
- **A date.** A weekday in the first half of 2026, inside the same
  2026-01-05 to 2026-06-30 range the transcripts use.
- **A subject that fits the company.** Widget Makers Incorporated designs and
  manufactures industrial sensors. Customers, suppliers, competitors, and
  product names may be invented freely; people may not.

## The nine documents

### Word

| File | Author | Date | What it is |
| --- | --- | --- | --- |
| `xt-9-rev-b-thermal-qualification-report.docx` | Sofia | 2026-03-12 | Qualification report on thermal drift in the XT-9 Rev B, written after the firmware workaround was tested. Scope, method, results per test chamber, findings, recommendation. |
| `iec-62443-certification-readiness-assessment.docx` | Callum | 2026-03-02 | Where the company stands against IEC 62443 and what closing the gap costs. Regulatory scope, gap analysis by requirement family, remediation plan, timeline and cost. |
| `contract-manufacturer-transition-plan.docx` | Devon | 2026-04-15 | A plan for moving board assembly to a second contract manufacturer. Current state, candidate evaluation, transition phases, risks. |

### PowerPoint

| File | Author | Date | What it is |
| --- | --- | --- | --- |
| `q1-board-review.pptx` | Priya | 2026-04-02 | The quarter presented to the board: revenue against plan, pipeline, the state of the product line, what went wrong and what is being done about it. |
| `fieldsense-200-launch-campaign-plan.pptx` | Nadia | 2026-02-10 | The go-to-market plan for the FieldSense 200 Series launch — positioning, channels, timeline, budget, what success is measured as. |
| `brannock-refinery-account-recovery-briefing.pptx` | Elena | 2026-04-14 | An internal briefing on a damaged account: what happened, where it stands, the recovery plan, and what is being asked of other teams. |

### Excel

| File | Author | Date | What it is |
| --- | --- | --- | --- |
| `q1-sales-pipeline.xlsx` | Jamal | 2026-03-30 | **Three sheets.** Open opportunities with stage, value, and close date; closed-won deals; a month-by-month forecast roll-up. |
| `proximasense-x4-bom-cost.xlsx` | Renata | 2026-01-12 | A bill of materials for the ProximaSense X4 with per-line quantities, unit costs, extended costs, and supplier. |
| `support-ticket-sla-log.xlsx` | Theo | 2026-06-01 | Support tickets with opened and resolved dates, severity, the SLA target, and whether it was met. |

## How these relate to the transcripts

Six of the nine sit within a week of a meeting on the same subject. That is
deliberate. A corpus of transcripts alone can only be asked what was said in a
room; a corpus that also holds the report that came out of the room can be
asked questions that need both, which is the thing worth testing once more
than one format is in the store.

| Document | Meeting | Relationship |
| --- | --- | --- |
| `xt-9-rev-b-thermal-qualification-report.docx` | XT-9 Rev B Thermal Drift – Firmware Workaround Feasibility (2026-03-05) | Reports the results of what the meeting proposed |
| `iec-62443-certification-readiness-assessment.docx` | IEC 62443 Compliance Certification – Scope and Timeline (2026-02-24) | Written up after the scope was agreed |
| `fieldsense-200-launch-campaign-plan.pptx` | Q1 Marketing Launch – FieldSense 200 Series (2026-02-03) | The plan the meeting asked for |
| `brannock-refinery-account-recovery-briefing.pptx` | Customer Escalation – Brannock Refinery Account (2026-04-08) | Briefed after the escalation |
| `proximasense-x4-bom-cost.xlsx` | Sensor Unit Cost Review – ProximaSense X4 (2026-01-14) | The costs the meeting reviewed, dated two days before it |
| `support-ticket-sla-log.xlsx` | Support Backlog and Ticket SLA Review (2026-06-02) | The data the meeting reviewed, dated the day before it |

`contract-manufacturer-transition-plan.docx`, `q1-board-review.pptx`, and
`q1-sales-pipeline.xlsx` are the exceptions. The transition plan stands
entirely alone, so retrieval is not always leaning on a meeting to make sense
of a document. The board review and the pipeline workbook draw on several
meetings at once rather than one.

**Documents do not cite meetings.** A related document covers the same
subject and uses the same figures; it never says "as discussed on the 5th" or
names a meeting. This is the rule the transcripts already follow with each
other, and it holds here for the same reason: a corpus of independent
snapshots is what makes retrieval do the joining, rather than the documents
having pre-joined themselves.

## Imperfections

`docs/planted-imperfections.md` explains why the transcript corpus is
deliberately flawed. The office documents carry that further, and one of these
is only possible once a second format exists:

1. **A document contradicted by a later meeting.** One of the nine states a
   figure — a unit cost, a yield, a close date, a headcount — that a
   later-dated transcript states differently. Neither acknowledges the other.
   This is the stale-document failure, and it is the most realistic one in a
   real corpus: the document was right when it was written.
2. **A number that appears in two formats and disagrees.** A figure in a
   workbook and the same figure quoted in a deck do not match. A reader
   checking one against the other finds the discrepancy; retrieval on its own
   will happily return either.
3. **Uneven depth.** Some documents are thorough and some are thin, the way
   they are when one was written under deadline. Nothing marks the difference.

Record what actually lands in `docs/planted-imperfections.md` after the files
are generated, the same way the transcript batch is recorded there.

## Authorship coverage

Nine documents and ten people means one person authors nothing. That is
Marcus, who appears throughout the transcripts as Head of Hardware
Engineering but writes none of the nine. It is left that way on purpose — it
is unremarkable for someone to be present in every discussion and author no
documents — and is noted here so a reader does not take it for an oversight.
