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
run: read the batch, find the four, and record them here. Nothing has been
generated yet.

| Imperfection | Meetings | What it is |
| --- | --- | --- |
| _(none yet)_ | | |

Record enough to find it again — the slugs involved and the fact in dispute —
but not so much that this file becomes a second copy of the corpus.
