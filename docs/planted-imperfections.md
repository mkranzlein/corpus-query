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

Asking for an imperfection is not the same as getting one. One of the four
landed several times over, two landed in a weaker form than they were asked
for, and one did not land at all. That is recorded below rather than quietly
omitted, because a list of intended flaws that is really a list of requested
flaws would be worse than no list: it would have us testing against failures
the corpus does not actually contain.

### Batches 1 and 2 — ten meetings, 2026-01-22 to 2026-06-11

The ten meetings were generated in two batches of five, and each batch was
asked for all four imperfections. Which meeting came from which batch was not
recorded, so the ten are read together here.

| Imperfection | Meetings | What it is |
| --- | --- | --- |
| Contradictory facts — **landed** | `q2-pricing-review-gx-7-and-rv-2-list-price-adjustment` (2026-03-11) → `nadia-handoff-rv-2-launch-campaign-assets-review` (2026-05-05), `rv-2-pre-launch-readiness-check` (2026-05-19) | In March, Nadia says the RV-2's $189 introductory price "is in the campaign brief, in the pre-launch materials we've shared with two press contacts." In May she has $179 on the one-pager, and says it is "what was in the notes I got from the pricing meeting"; two weeks later she has "$179 in every piece of campaign material I've built." |
| Contradictory facts — **landed** | `rv-2-pre-launch-readiness-check` (2026-05-19) → `rv-2-firmware-1-0-0-go-no-go-decision` (2026-05-22) | The readiness check opens "five weeks from the RV-2 ship date," has firmware 1.0.0 soaking on twelve units, and has the 400-unit first run starting "on June 2nd at the contract manufacturer." Three days later the go/no-go meeting reports seventy-two hours of soak "on six units," has the same run starting "Monday," and ships it on June 2. |
| Contradictory facts — **landed** | `quennick-escalation-firmware-defect-on-mx-3-units` (2026-04-09) → `firmware-lifecycle-policy-and-version-support-commitments` (2026-06-11) | April decides that firmware 2.4.2 goes to every MX-3 customer on 2.4.1 at once. In June, Sofia says "Quennick is on MX-3 firmware 2.4.1" and reasons about their support commitment on that basis. |
| Unanswered question — **weakly** | `nadia-handoff-rv-2-launch-campaign-assets-review` (2026-05-05), `rv-2-pre-launch-readiness-check` (2026-05-19) | Elena asks "Where did $179 come from?" and the only answer is that it was in Nadia's notes. Two weeks later Nadia asks "When did that change?" and Elena says it didn't, as far as she knows. Neither meeting, nor any other, settles where the $179 came from; both move on to correcting the materials. Every other direct question in the ten gets an answer, or a "don't know" that turns into an action item — Elena asking whether Hessanby is talking to competitors (2026-04-23) — or into something to raise on a customer call — how many faulted units Quennick can reach (2026-04-09). |
| Reversed decision — **weaker than asked for** | `q2-pricing-review-gx-7-and-rv-2-list-price-adjustment` (2026-03-11) → `q1-financial-close-and-margin-review` (2026-04-23) | March raises GX-7 list to $239 and agrees to "hold the line on discounts, and accept that we lose some of the deals we've been buying with price." In April, the Hessanby renewal gets a $198 floor — 17% below the new list, beyond the ten-percent standard discount — without any reference to the March position. What reverses is a policy rather than a stated decision, and April frames it as a floor, not a change of course. |
| Uneven quality — **did not land** | — | All ten read as tidy transcripts. Turn length varies, and there are a few self-interruptions — Nadia in the readiness check: "I don't — okay, I'm not going to relitigate this right now" — but no transcript rambles, trails off, or lands mid-thought. |

### What this means for the corpus

The failure the corpus tests best is the stale or conflicting record on a
single fact. The RV-2 introductory price is $189 in three meetings and $179 in
one person's account of her own materials, and — see the office documents
below — $179 in the one written plan. The RV-2 production schedule and the
firmware running at Quennick each have two incompatible versions, a few days
or two months apart, with nothing in either meeting flagging the other.

The failure it tests least is the unanswerable question. The origin of the
$179 is the one thing the record raises and never settles; everything else
asked in a meeting is answered in the same meeting. A corpus-wide "nothing
here settles this" is still best provoked with a question about something the
company never discussed, which is what the smoke queries do.

## Office documents

Nine office documents — three Word documents, three PowerPoint decks, three
Excel workbooks — sit alongside the transcripts under `data/office/`.
`data/office_files_guidance.md` asked for three imperfections across the
nine: a document contradicted by a later meeting, a number that appears in a
workbook and a deck and disagrees, and uneven depth. It also asked that
documents never cite meetings, so any contradiction across formats has to be
found by comparing figures directly, the way retrieval would.

This section reads the nine committed files and records what actually landed,
the same way the transcripts are recorded above. All three landed.

### What was planted

| Imperfection | Documents | What it is |
| --- | --- | --- |
| Document contradicted by a later meeting — **landed** | `rv-2-launch-campaign-plan.pptx` (Nadia, 2026-03-04) → `q2-pricing-review-gx-7-and-rv-2-list-price-adjustment` (2026-03-11), `nadia-handoff-rv-2-launch-campaign-assets-review` (2026-05-05), `rv-2-pre-launch-readiness-check` (2026-05-19) | Slide 5, "The Introductory Offer," and its notes give an introductory price of $179 for ninety days, then $209. A week later the pricing review settles $189 and says $189 is what the campaign brief already carries, and both May meetings treat $189 as the agreed number. The deck is the only document that backs Nadia's $179, so a question about the RV-2 launch price has a written source on each side. |
| A number that appears in a workbook and a deck and disagrees — **landed** | `q1-sales-pipeline.xlsx` (Jamal, 2026-03-30) → `q1-board-review.pptx` (Priya, 2026-04-28) | Slide 6, "Q2 Pipeline by Stage," gives $486K of qualified pipeline closing in Q2, $301K weighted, $171K in Commit, and a $535K base-case forecast. The workbook's `Q2 Forecast by Month` sheet totals $441,964 qualified, $268,586 weighted, $157,640 in Commit, and a $512,586 base case. Named deals disagree too. The slide has the Quennick GX-7 expansion at $64.2K in Commit; the `Open Opportunities` sheet has it as `OPP-1201`, 300 units at $192.60, $57,780, in Negotiation. The slide has Kilnwarden's MX-3 substation refresh at $38.2K in Commit; the sheet has `OPP-1215` at $42,930, in Proposal and forecast as Best Case. The slide's figure for Ivelmoor's plant two rollout, $42.4K, matches the sheet's `OPP-1204`, but the slide calls it Best Case and the sheet has it at Evaluation, forecast as Pipeline. `quennick-account-recovery-briefing.pptx` (Elena, 2026-04-15) quotes the workbook's $57,780, so the two decks disagree with each other as well. |
| Uneven depth — **landed, among the three Word documents** | `ce-marking-readiness-assessment.docx` (Callum, 686 words) vs. `mx-3-firmware-2-4-2-soak-test-report.docx` (Sofia, 1,889 words) and `end-of-line-test-station-upgrade-plan.docx` (Devon, 1,872 words) | The CE assessment covers directives, gaps, a lab plan, timeline, and cost in about a paragraph each. Its Testing section says "A detailed breakdown by test is given in the next section," and the next section is a four-sentence lab plan with no breakdown. The soak test report tabulates results per rig and idle duration, and the test station plan costs three options line by line. The three decks (13 to 15 slides, each with comparable speaker notes) and three workbooks show no equivalent spread. |

### What this means for the corpus

The stale-document failure now has a written source on the wrong side: a
question about the RV-2 launch price can be answered from a dated, authored
plan that every later meeting contradicts. The workbook-versus-deck
contradiction gives retrieval several independent ways to return a wrong
pipeline number with an authoritative-looking source — two totals, two named
deals, and a forecast category — and a third document, the account briefing,
that sides with the workbook against the board deck.
