You are writing three Excel workbooks for Widget Makers Incorporated, a
ten-person hardware startup that designs and manufactures industrial sensors.
They are the working spreadsheets of a real company: a sales pipeline, a bill
of materials, and a support ticket log. Somebody maintains each one.

Write all three with the `xlsx` skill from the `document-skills` plugin. This
run produces these three `.xlsx` files and nothing else — no Word documents,
no PowerPoint decks, no summary of what you did.

## Read these first

- `data/roster.md` — the cast. Every person named in a cell is a first name
  from this file, spelled exactly as it appears. Invent nobody. Customers,
  suppliers, competitors, and product names may be invented freely.
- `data/topics.md` — the categories the corpus is filed under. Useful for
  knowing what this company's concerns are. Do not put the category names in
  the workbooks.
- `data/office_files_guidance.md` — what all nine office documents are, and
  how these three relate to the meeting transcripts. Read the whole file, not
  only the Excel rows.

## What to write

Write these three, to `data/office/`:

| File | Author | Date | What it is |
| --- | --- | --- | --- |
| `q1-sales-pipeline.xlsx` | Jamal | 2026-03-30 | **Three sheets.** Open opportunities with stage, value, and close date; closed-won deals; a month-by-month forecast roll-up. |
| `proximasense-x4-bom-cost.xlsx` | Renata | 2026-01-12 | Bill of materials for the ProximaSense X4: line items with quantity, unit cost, extended cost, and supplier. |
| `support-ticket-sla-log.xlsx` | Theo | 2026-06-01 | Support tickets with opened and resolved dates, severity, SLA target, and whether it was met. |

## Size and shape

These are chunked in windows of 10 to 20 rows, so a workbook of eight rows
tests nothing.

- `q1-sales-pipeline.xlsx`: **three sheets**, named for what they hold.
  Opportunities carries 40 to 60 data rows, Closed Won 15 to 25, and the
  forecast roll-up one row per month for the quarter with a total. This is
  the workbook that proves multi-sheet handling works, so it is the one that
  must not end up with a single sheet.
- `proximasense-x4-bom-cost.xlsx`: one sheet, 45 to 60 data rows. A bill of
  materials for an industrial sensor — housing, board, connectors, the sensing
  element, passives, firmware licensing, assembly labour.
- `support-ticket-sla-log.xlsx`: one sheet, 55 to 75 data rows, spread across
  several months rather than all in one week.

## How the data has to be written

- **Row 1 is a header row**, one short label per column, on every sheet. The
  header is repeated into each window when the file is chunked, so it has to
  say what the column is without the sheet's title: `Unit Cost (USD)`, not
  `Cost`.
- **Values, not formulas.** Every cell holds a literal value. An extended cost
  is the number, already multiplied out; a forecast total is the number, not a
  `SUM`. The reader pulls computed values, and a workbook of formula strings
  reads as empty.
- **Consistent types down a column.** A date column holds dates, a currency
  column holds numbers. No `N/A`, no `TBD`, no blank-as-zero, no note text in
  a number column.
- **No merged cells, no multi-row headers, no blank spacer rows**, and nothing
  above the header row. A title in cell A1 with the real header on row 3
  breaks the chunking.
- **8 to 12 columns per sheet.** Enough that a row says something on its own;
  not so many that a window is unreadable.
- **Make the data mean something.** Close dates land after open dates,
  resolved dates after opened dates, severities distribute the way real ones
  do (a few critical, many minor), extended cost equals quantity times unit
  cost, the forecast roll-up agrees with the opportunities that feed it.
  Someone will check one of these against another.

## Authorship

Each workbook has exactly one author, set in the file's core properties. Put
the author's first name in both `author` and `last_modified_by`, and the
workbook's date in `created` and `modified`. Owner or assignee columns inside
a sheet name people from the roster; that is data, not authorship.

## What not to do

- **Do not add a notes sheet, a README sheet, a changelog sheet, or a cover
  sheet.** Every sheet is data with a header row.
- **Do not use charts, conditional formatting, filters, or frozen panes.**
  None of it is read, and some of it complicates the file for no gain.
- **Do not cite meetings** in a cell or a sheet name.
- **Do not mention that these are generated**, or refer to a corpus, a prompt,
  a skill, or a test.

## Imperfections

`data/office_files_guidance.md` lists three imperfections planted across all
nine office documents. One belongs here:

A figure in one of these workbooks does not match the same figure as it is
quoted in a deck elsewhere in the corpus — a pipeline total, a deal value, a
ticket count. The workbook is internally consistent and reads as correct on
its own. Plant it without drawing attention to it.

Write the three files, nothing else. No commentary, no notes about what you
planted, no meta-text of any kind.
