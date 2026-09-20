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
one of which — a figure that disagrees between a workbook and a deck — is the
numeric contradiction this batch did not produce.
