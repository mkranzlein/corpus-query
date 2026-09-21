# Telling it when it is wrong

Three kinds of record, deliberately not one.

A **gap** is detected rather than reported: whenever the record does not
settle a question, the service writes one, carrying the routing suggestion
when there was one to make. Nobody has to remember to file it.

A **correction** is what a person says the answer got wrong, and what is true
instead. Both halves are required.

**Feedback** is a thumbs up or down, with an optional note. A bare thumbs down
is feedback rather than a correction: it says an answer was bad and carries
nothing anybody can act on, and a queue of things to act on that is full of
them wastes the reader's time.

All three hang off the `answer_id` that came back with the answer. That is
what lets a correction written a week later name the answer it corrects,
rather than a question that may have been asked more than once:

```bash
curl -s localhost:8000/corrections \
  -H 'content-type: application/json' \
  -d '{"answer_id": "5f1c0b7a2c1e4d8fa0b9c7d6e5f43210",
       "what_was_wrong": "It said the firmware freeze is March 12th.",
       "what_is_right": "The freeze moved to March 19th."}'

curl -s localhost:8000/feedback \
  -H 'content-type: application/json' \
  -d '{"answer_id": "5f1c0b7a2c1e4d8fa0b9c7d6e5f43210",
       "verdict": "down", "note": "cited the wrong meeting"}'
```

An id that does not name an answer this service gave is a `404`. Storing it
anyway would make a row nothing could ever read back.

A correction can also be typed into the conversation, as the next message on
the same thread:

```bash
curl -s localhost:8000/answer \
  -H 'content-type: application/json' \
  -d '{"thread_id": "…",
       "question": "No, that is wrong. The freeze moved to March 19th."}'
```

The agent recognizes a message that says an earlier answer was wrong and
what is right instead, and records it against that answer's id in the same
table, without searching. Its reply says what it recorded, and the response's
`correction` field carries the row. A question about an answer, or
disagreement that does not say what is right, is not recorded. When the
conversation holds more than one answer and the message does not make clear
which one it means, the agent asks rather than guessing.

Read the three back most recent first, each row carrying the question that
produced it and the answer that was given, so a reader working through them
does not need a second call per row:

```bash
curl -s localhost:8000/gaps
curl -s localhost:8000/corrections
curl -s localhost:8000/feedback
```

```jsonc
{
  "gaps": [
    {
      "id": 4,
      "answer_id": "5f1c0b7a2c1e4d8fa0b9c7d6e5f43210",
      "created_at": "2026-03-12T16:04:11.238Z",
      "thread_id": "bafccadb164e4447b21f7a8899f11390",
      "question": "What tolerance did we set on the rev B connector?",
      "answer": "The record does not give a tolerance for the rev B connector.",
      "abstained": true,
      "citations": [ /* the passages the answer rested on */ ],
      "reviewed_at": null,
      "routing": { /* who to ask, as it was suggested at the time */ }
    }
  ]
}
```

`?limit=` bounds a read; the default is 50 and the ceiling is 200.

## The review queue

Open `http://localhost:8000/review` for all three kinds in one list, newest
first. You can narrow it to one kind, and each row opens to the full record.
The page is for someone reading through what the system got wrong and looking
for patterns, not for the people asking questions, so the question page does
not link to it.

Its one write is the review mark. `reviewed_at` is null until someone marks
the item seen, and marking it again keeps the first time. Setting it back to
`false` returns the item to the new ones. The same thing over HTTP, with
`GET` on the same path to read one record:

```bash
curl -s -X PATCH localhost:8000/corrections/3 \
  -H 'content-type: application/json' -d '{"reviewed": true}'
```

A usage database from before the review mark existed is upgraded in place the
first time the service opens it. Its rows are kept and come up as new.

**Corrections are recorded, not applied.** Nothing here feeds them back into
retrieval or generation, and an answer to the same question tomorrow will be
the same answer. That is a deliberate stopping point: the records are for
people to read. Applying them would take three things this does not have —
a way to decide which corrections are still true when two of them disagree, a
way to attach one to the passages it contradicts rather than to the question
that surfaced it, and a way to tell an answer's reader that part of what they
are reading came from a correction rather than from the record. Feeding
unreviewed corrections into answers without those is a way to make the system
confidently wrong in a new direction.
