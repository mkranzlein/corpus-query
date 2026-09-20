You are tidying the category list a company files its meetings under.

The list was built up one meeting at a time, so it has accumulated pairs that
mean the same thing — "Supply Chain" and "Supply Chain Risk", "Hiring" and
"Recruiting". Every meeting filed under one of them should be filed under a
single surviving name instead.

## The categories

{{categories}}

## What to return

- One group per set of names that mean the same thing. Return no groups at
  all if the list is already clean; that is a fine answer.
- In each group, `keep` is the surviving name and `merge` lists the others.
  Keep the more general of the names, the one that will still fit a meeting
  that is only loosely about it.
- Every name you use has to appear in the list above, spelled exactly as it
  appears there. Do not invent a new name to merge two old ones into.
- Merge only names that are the same category under two labels. Two
  categories that are merely related — "Firmware" and "Hardware", "Pricing"
  and "Contracts" — stay separate. Collapsing those loses the distinction
  that makes the list worth having.
- A name belongs to at most one group.
