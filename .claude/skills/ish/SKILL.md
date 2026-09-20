---
name: ish
description: Write a well-scoped GitHub issue, with clarifying questions first. Use when the user says "ish", "write an issue", "file an issue", or describes work that needs scoping before it can be implemented. For fast capture without the back-and-forth, use quickish instead.
argument-hint: [rough description of the work]
---

# ish

Turn a rough idea into an issue an implementer agent can pick up without
guessing. Scoping is the point of this skill — the back-and-forth is the value,
not overhead.

## Process

### 1. Interrogate before drafting

Do not draft on the first pass. Read the repository first to ground the
questions in what actually exists, then ask about whatever would change the
implementation. Typically:

- **Boundaries** — what is explicitly *not* in this issue? Which nearby thing
  is a separate issue?
- **Acceptance** — how will we know it's done? What would you check?
- **Decisions not yet made** — anything an implementer would otherwise have to
  invent: a schema, a threshold, a name, an interface.
- **Dependencies** — does this need another issue landed first?
- **Failure behavior** — what should happen in the bad case?

Ask only what matters. Three sharp questions beat ten generic ones. Use
AskUserQuestion when the options are enumerable; ask in prose when they aren't.

### 2. Draft the issue

**Title** — imperative, specific, under ~70 characters.

**Body**, in this shape:

```markdown
## Description

What needs to exist and why. Enough context that someone who wasn't in the
conversation understands the motivation.

## Acceptance criteria

- [ ] Specific, checkable statements
- [ ] Each one verifiable by running something or reading something
- [ ] Not "works correctly" — say what correct means here

## Out of scope

What this issue deliberately does not cover, and where it goes instead.

## Notes

Decisions already made, constraints, links to related issues. Anything that
stops an implementer from re-deciding something.
```

### 3. Present the draft

Show the full title and body and wait. Expect revisions — that's normal for
this skill, not a failure. Iterate until the user approves.

### 4. Create it

`gh issue create` with the approved title, body, and a milestone. Ask which
milestone if it isn't obvious from the content. Report the issue number and
URL.

Do not create the issue before the user approves the draft.
