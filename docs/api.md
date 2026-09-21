# Asking over HTTP

The page at `/` is one client of these endpoints, and `curl` is another.
Everything the page does goes through them, so everything here can be done
from a terminal too. The service has to be running first; see the
[Quickstart](../README.md#quickstart).

## Ask it something

```bash
curl -s localhost:8000/search \
  -H 'content-type: application/json' \
  -d '{"query": "What is the lead time on the PM-4?", "limit": 3}'
```

```jsonc
{
  "query": "What is the lead time on the PM-4?",
  "results": [
    {
      "rank": 1,
      "chunk_id": 101,
      "text": "[Marcus]: There's a potential revision on the power management section. We've been looking at swapping the Kessendra PM-4 for the Tolvane equivalent because Kessendra lead times have stretched to sixteen weeks. ...\n[Renata]: Can you flag me when you have something more concrete? Even a range would help.\n...",
      "document_slug": "gx-7-unit-cost-review-and-supplier-decision",
      "source_kind": "transcript",
      "title": "GX-7 Unit Cost Review and Supplier Decision",
      "document_date": "2026-01-22",
      "author": null,
      "attendees": ["Priya", "Marcus", "Renata", "Devon"],
      "location": "turns 24-27",
      "span_start": 24,
      "span_end": 27,
      "topics": ["Manufacturing", "Supply Chain", "Pricing"],
      "time_sensitivity": "near_term",
      "business_impact": "moderate",
      "rerank_score": 8.41
    }
    // ...two more, ranks 2 and 3
  ],
  "confidence": {
    "top_score": 8.41,
    "margin": 3.17,
    "lexical_dense_agree": true,
    "unmatched_terms": []
  }
}
```

The confidence block is about the results, not part of them. `top_score` is
the reranker's score for the best result and `margin` is its lead over the
second — a high score with no margin means several passages are equally
plausible. `lexical_dense_agree` says whether keyword search and vector search
independently picked the same chunk first, before anything fused or reranked
them. `unmatched_terms` lists query words that appear nowhere in the corpus,
which is usually a misspelling or a name that never came up.

Nothing here is a threshold. The signals are reported so a caller can weigh
them; this endpoint does not decide that an answer is too weak to give.

A question the corpus has nothing to say about is a `200` with an empty
`results` list, not a `404`. Nothing matching is an answer. A missing or blank
`query` is a `422` that names the problem, and `limit` has to be between 1 and
50.

Interactive API documentation, generated from the same models that validate
the request, is at <http://localhost:8000/docs>.

## Ask for an answer instead

```bash
curl -s localhost:8000/answer \
  -H 'content-type: application/json' \
  -d '{"question": "What did we decide about the RV-2 introductory price?"}'
```

```jsonc
{
  "question": "What did we decide about the RV-2 introductory price?",
  "answer": "The RV-2 launches at an introductory $189 for ninety days, then steps to $209 list ...",
  "citations": [
    {
      "chunk_id": 113,
      "document_slug": "q2-pricing-review-gx-7-and-rv-2-list-price-adjustment",
      "source_kind": "transcript",
      "title": "Q2 Pricing Review — GX-7 and RV-2 List Price Adjustment",
      "document_date": "2026-03-11",
      "author": null,
      "attendees": ["Priya", "Elena", "Renata", "Jamal", "Nadia"],
      "location": "turns 22-30"
    }
    // ...the rest of what it read
  ],
  "searches": 1,
  "abstained": false,
  "routing": null,
  "thread_id": "bafccadb164e4447b21f7a8899f11390",
  "answer_id": "5f1c0b7a2c1e4d8fa0b9c7d6e5f43210"
}
```

Behind that is a LangGraph agent holding one tool: `/search`, which it reaches
over HTTP the same way you just did. Whether it searches at all, and how many
times, is its decision. A question with two subjects is two searches. A
question the conversation already answered is none. A question the corpus
could not hold — the capital of France — is declined without a search, which
is why `searches` is part of the response rather than an implementation
detail.

**Not knowing is an answer.** Retrieval always returns its best few passages,
so the agent's job includes deciding that they do not actually address what
was asked and saying so, rather than summarizing whatever came back. That
comes back as a `200`, like any other answer, with `abstained` set to `true`.
A question declined without a search, as out of scope, is not an abstention:
the record was never going to hold it, so `abstained` stays `false`.

A citation says where a passage came from but not what it says. Read the
passage itself, and the topics, time sensitivity, and business impact derived
for its document, by the citation's `chunk_id`:

```bash
curl -s localhost:8000/chunks/113
```

The body is a search result's fields without `rank` and `rerank_score`, since
a passage read on its own was not ranked against anything. An id the corpus
does not hold is a `404`.

## Not knowing also suggests who to ask

A decline is a better place to stop than a made-up answer, and still a poor
place to stop. The passages that scored well without settling the question
each name the person who wrote them or the people who were in the room, so
the search that failed already identifies who would know. When the agent
searched and could not answer from what came back, `routing` carries that:

```jsonc
{
  "answer": "The record does not say which sites the two remaining faulted Quennick units are at. ...",
  "routing": {
    "candidates": [
      {
        "name": "Sofia",
        "role": "Firmware Engineer",
        "department": "Engineering",
        "passages": 4,
        "evidence": [
          {
            "chunk_id": 170,
            "document_slug": "mx-3-firmware-2-4-2-soak-test-report",
            "source_kind": "docx",
            "title": "MX-3 Firmware 2.4.2 Soak Test Report",
            "document_date": "2026-04-14",
            "author": "Sofia",
            "attendees": [],
            "location": "Field Rollout"
          }
          // ...the rest of what put Sofia here
        ]
      }
      // ...Theo and Elena, one passage each
    ],
    "question": "I was looking for where Quennick's two remaining faulted MX-3 units are installed. The available documentation says nine of the eleven faulted units have been power cycled and updated and that the last two are at remote sites with visits scheduled, but it does not name the sites. Which sites are the two remote faulted Quennick units at?"
  }
}
```

Candidates are ranked by how much of the matched material each person wrote
or attended, and every name is resolved against `data/roster.md`, so a
suggestion is a colleague rather than whatever string sat in a file's
properties. `evidence` is the same citation shape an answer's claims carry,
which is what makes a suggestion as traceable as an answer.

`question` is the user's question restated to stand on its own, with the
context that made it unanswerable, for someone who has not seen the original.
It is text to edit. Nothing is sent anywhere.

The suggestion is recorded, though. A question the record did not settle is a
gap, and the service files one itself, with the suggestion exactly as it was
made — see [Telling it when it is wrong](feedback.md).

A question the corpus answers gets no routing, and neither does one declined
without a search: the capital of France is not something anyone here should
be asked. Routing is for the questions this organization ought to be able to
answer and the record does not.

## Conversations

`thread_id` is the conversation. Send it back with the next question and the
agent answers against everything already said — which is how a follow-up gets
answered without searching again:

```bash
curl -s localhost:8000/answer \
  -H 'content-type: application/json' \
  -d '{"question": "Who owns that?", "thread_id": "bafccadb164e4447b21f7a8899f11390"}'
```

Conversations are checkpointed to disk, so a thread survives a restart. That
goes in a second SQLite file, `data/usage.db`, and not into the corpus. The
corpus is a committed artifact and stays read-only in normal use; the usage
database is local, is not committed, and is created the first time you ask a
question. The [gaps, corrections, and feedback](feedback.md) go in that same
file, and so does the [trace](tracing.md) of every question.
Deleting it costs you the threads and the records it held and nothing else.
Point `--usage-db` somewhere else to keep it elsewhere.

## Watching it work

A local answer can take tens of seconds, most of it spent waiting on the
model. Ask for `text/event-stream` and the same endpoint reports each step as
it happens, as [server-sent
events](https://html.spec.whatwg.org/multipage/server-sent-events.html), and
sends the answer last:

```bash
curl -sN localhost:8000/answer \
  -H 'content-type: application/json' \
  -H 'accept: text/event-stream' \
  -d '{"question": "What did we decide about the RV-2 introductory price?"}'
```

```
event: started
data: {"thread_id": "bafccadb164e4447b21f7a8899f11390"}

event: drafting
data: {}

event: searching
data: {"query": "RV-2 introductory price decision"}

event: searched
data: {"query": "RV-2 introductory price decision", "citations": [{"chunk_id": 113, ...}, ...]}

event: drafting
data: {}

event: verifying
data: {}

event: verified
data: {"verification": null, "redraft": false}

event: routing
data: {}

event: answer
data: {"question": "What did we decide about the RV-2 introductory price?", "answer": "The RV-2 launches at an introductory $189 for ninety days, then steps to $209 list ...", ...}
```

`-N` stops curl buffering, so each event prints as it arrives. What each one
means:

| Event | When | Data |
|---|---|---|
| `started` | The question was received. | `thread_id`, known before anything runs. |
| `drafting` | The model was asked to answer. It may ask for a search instead, so this comes again after a search and after a rejected draft. | — |
| `searching` | Retrieval started. | `query`, what the model asked to search for. |
| `searched` | Retrieval returned. | `query`, and `citations` in the shape an answer cites them. |
| `verifying` | The draft's claims are being checked against the passages. Skipped when nothing was cited. | — |
| `verified` | The check finished. | `verification`, null when every claim held up; `redraft`, whether the model is drafting again. |
| `routing` | The answer is being judged against the question, to decide who to ask if it did not settle it. Skipped when nothing was cited. | — |
| `correcting` | The message was taken as a correction of an earlier answer and is being recorded. Comes instead of everything from `searching` on. | — |
| `answer` | Done. | Exactly the JSON body the request without the header gets. |
| `error` | The run failed partway. | `detail`, what went wrong. |

The stream ends after `answer` or `error`. Once events have started the status
is already `200`, so a failure arrives as an `error` event rather than a status
code, with the traceback in the service's log as usual; a question that fails
validation is still a `422` before any stream starts. A client that
disconnects stops the run where it is, and nothing is recorded, since nothing
was answered. The thread stays usable: the next question asked on it clears
the half-finished turn and starts clean.

The events are steps, not tokens. The answer arrives whole, in `answer`.

Without the header — or with curl's default `*/*` — nothing changes: the
requests above get the single JSON response they always have.

The stream is a response to a `POST`, so a browser reads it with `fetch` and
the response body's reader rather than with `EventSource`, which only makes
`GET` requests.
