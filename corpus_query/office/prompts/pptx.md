You are writing three PowerPoint decks for Widget Makers Incorporated, a
ten-person hardware startup that designs and manufactures industrial sensors.
They are internal decks from the working life of a real company: a quarter
presented to the board, a launch plan, and a briefing on an account in
trouble. Somebody built each one to stand up and present it.

Write all three with the `pptx` skill from the `document-skills` plugin. This
run produces these three `.pptx` files and nothing else — no Word documents,
no Excel workbooks, no summary of what you did.

## Read these first

- `data/roster.md` — the cast. Every person named on a slide or in the notes
  is a first name from this file, spelled exactly as it appears. Invent
  nobody. Customers, suppliers, competitors, and product names may be invented
  freely.
- `data/topics.md` — the categories the corpus is filed under. Useful for
  knowing what this company's concerns are. Do not put the category names in
  the decks.
- `data/office_files_guidance.md` — what all nine office documents are, and
  how these three relate to the meeting transcripts. Read the whole file, not
  only the PowerPoint rows.

## What to write

Write these three, to `data/office/`:

| File | Author | Date | What it is |
| --- | --- | --- | --- |
| `q1-board-review.pptx` | Priya | 2026-04-02 | The quarter presented to the board: revenue against plan, pipeline, the state of the product line, what went wrong and what is being done about it. |
| `fieldsense-200-launch-campaign-plan.pptx` | Nadia | 2026-02-10 | Go-to-market plan for the FieldSense 200 Series launch — positioning, channels, timeline, budget, how success is measured. |
| `brannock-refinery-account-recovery-briefing.pptx` | Elena | 2026-04-14 | An internal briefing on a damaged account: what happened, where it stands, the recovery plan, what is being asked of other teams. |

## Authorship

Each deck has exactly one author, set in the file's core properties. Put the
author's first name in both `author` and `last_modified_by`, and the deck's
date in `created` and `modified`. No deck has a second author or a
contributors list. Other people are named on slides and in notes where it
makes sense; they did not build the deck.

## Speaker notes are the point

A slide is a fragment. "Margin down 4 points" is not an answer to anything —
the sentence that actually states the claim is the one the presenter says out
loud, and in this corpus that sentence lives in the speaker notes.

- **Most slides carry notes**, and the notes are the substance: 60 to 150
  words of what the presenter says when that slide is up. Complete sentences.
- The notes explain the slide rather than repeating it. If the slide says
  "Q1 revenue: $1.34M, 82% of plan", the notes say why it landed there, which
  deals slipped, and what that means for the next quarter.
- A title slide, a section divider, or a closing slide may have no notes. Any
  slide carrying a number or a claim has them.
- Notes name people and figures plainly. This is the part of the deck a
  question is most likely to be answered from.

## Structure

- 12 to 18 slides each, including a title slide and section dividers.
- Every slide has a real title that says what it is about. `Pipeline by Stage`
  rather than `Pipeline`, `Why Brannock Escalated` rather than `Background`.
  The title is half of what a citation shows a reader.
- Slide bodies are bullets, short phrases, and figures — how a slide is
  actually written. Do not write paragraphs on slides; that is what the notes
  are for.
- **No slide is empty.** Every slide has a title and either body text or
  notes. A slide that would carry only a chart or an image instead carries the
  figures as text.
- Give real numbers: revenue against plan, deal values, close dates, ticket
  counts, campaign spend, channel mix, week counts. Invent them freely, but
  make them specific and internally consistent within a deck.

## How they should read

The three are different kinds of document and should not sound alike. A board
review is measured, leads with the numbers, and does not hide the bad ones. A
launch plan is persuasive and forward-looking, with the budget it is asking
for made explicit. An account recovery briefing is candid about a mistake and
specific about who does what next.

## What not to do

- **Do not cite meetings.** These decks cover subject matter that meeting
  transcripts also cover, and they use the same figures, but they never say
  "as we agreed last week" or name a meeting. Each deck stands alone.
- **Do not describe images, charts, or diagrams you are not creating.** No
  `[chart placeholder]`, no "diagram here". Only text frames and notes are
  read out of these files.
- **Do not add a thank-you slide, a questions slide, or a confidentiality
  banner** with nothing on it.
- **Do not mention that these are generated**, or refer to a corpus, a
  prompt, a skill, or a test.

## Imperfections

`data/office_files_guidance.md` lists three imperfections planted across all
nine office documents. One belongs here:

A figure quoted in one of these decks does not match the same figure as it
appears in a workbook elsewhere in the corpus — a pipeline total, a deal
value, a ticket count. Neither acknowledges the other, and neither reads as
wrong on its own. Plant it without drawing attention to it.

Write the three files, nothing else. No commentary, no notes about what you
planted, no meta-text of any kind.
