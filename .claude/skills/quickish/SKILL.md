---
name: quickish
description: Capture a GitHub issue fast, with one review pass and no interrogation. Use when the user says "quickish", "quick issue", or wants something noted before it's forgotten. For work that needs scoping first, use ish instead.
argument-hint: [what to capture]
---

# quickish

Get an issue filed before the thought is lost. One draft, one review, done.

## Process

### 1. Draft immediately

No clarifying questions. Take what the user said, fill in what's obviously
implied, and write it. If something is genuinely ambiguous, note it in the
issue rather than asking — a filed issue with an open question beats an
unfiled one.

**Title** — imperative, specific, under ~70 characters.

**Body**:

```markdown
## Description

One or two sentences. What and why.

## Acceptance criteria

- [ ] What has to be true for this to be closed
```

Two or three criteria is usually right. If the list is growing past five, this
probably wanted `ish` — say so and offer to switch.

### 2. Present once

Show the draft and wait for approval. Keep it to that single pass; if the user
starts reshaping the scope, offer to switch to `ish` rather than iterating
here.

### 3. Create it

`gh issue create` with the approved title, body, and a milestone if one is
obvious. Report the issue number and URL.

Do not create the issue before the user approves the draft.
