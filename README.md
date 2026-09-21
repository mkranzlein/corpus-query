# corpus-query

[![CI](https://github.com/mkranzlein/corpus-query/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mkranzlein/corpus-query/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/mkranzlein/corpus-query/graph/badge.svg?token=ZGULR6SXPA)](https://codecov.io/gh/mkranzlein/corpus-query)

Ask a corpus of meeting transcripts and documents a question in plain English.
`/search` gives you back the passages that bear on it; `/answer` gives you an
answer written out of those passages, with the passages it rests on.

Each result carries where it came from — the document, its date, the turns or
the heading or the slide the passage spans — and the metadata derived from it
during ingestion: the topics it was filed under, how time sensitive it is, how
much business impact it carries. Alongside the results come confidence signals
about them.

## Where this sits

Two HTTP endpoints over one corpus. `/search` is hybrid retrieval — BM25 and
vector search, fused, then reranked by a cross-encoder. `/answer` is an agent
over that: it decides whether to search, how many times, and what the passages
add up to, and it says so when they add up to nothing.

The agent is a caller of `/search` rather than a replacement for it. It posts
to that endpoint like any other client, so the two can be asked the same
question and compared, and `curl` still reaches the ranking on its own.

What the corpus could not answer is kept. A question the record does not
settle is written down as a gap without anybody filing it, and `/corrections`
and `/feedback` take what a person has to say about an answer. All of it reads
back out of the same endpoints — see [Telling it when it is
wrong](#telling-it-when-it-is-wrong).

There is a browser application too, served at `/` by the same process. Today
it is a shell: it loads, and it reports what the service is running on. The
question box and the answer view are being built on top of it. Until they
land, `curl` is still the way to ask the corpus anything.

Everything runs on your machine by default: a SQLite document store on disk, a
local embedding model, a local reranking model, and a local chat model served
by Ollama. **Searching needs no AWS account, no Bedrock endpoint, and no API
key**, and neither does answering unless you ask for the hosted model by
name — see [Which model answers](#which-model-answers). A hosted model wrote
the transcripts and enriched them, but that work is done and its output ships
in the database. Building a corpus of your own is the one thing here that
needs credentials; see [Building a corpus](#building-a-corpus).

## Quickstart

Starting from nothing, on macOS:

```bash
# 1. Install uv, which manages the Python version and the dependencies.
brew install uv
# On Linux or Windows, use the installer instead:
# https://docs.astral.sh/uv/getting-started/installation/

# 2. Install the project, with the model stack.
git clone https://github.com/mkranzlein/corpus-query.git
cd corpus-query
uv sync --extra models

# 3. Fetch the embedding and reranking weights (~215 MB, once).
uv run scripts/fetch_models.py

# 4. Install Ollama and pull the chat model /answer runs on (~5.3 GB, once).
brew install ollama && ollama serve &
ollama pull granite4.1:8b

# 5. Start the service. The committed corpus at data/corpus.db is ready to query.
uv run scripts/serve.py
# The page is at http://127.0.0.1:8000, the endpoints are below it.
```

Note what is not in that list: Node. The browser application is built ahead of
time and the build is committed, so running the whole system takes Python and
nothing else. See [The committed
frontend](#the-committed-frontend).

Step 4 is only needed for `/answer`. `/search` ranks without a chat model, and
the service starts either way — a question asked of `/answer` with no Ollama
running is the one thing that fails.

It is also only needed for the local model, which is the default. To answer
from the hosted model instead, skip step 4, put a Bedrock key and a region in
`.env`, and name the backend when you start the service:

```bash
cat >> .env <<'EOF'
AWS_BEARER_TOKEN_BEDROCK=your-bedrock-api-key
AWS_REGION=us-east-1
EOF
CORPUS_QUERY_MODEL_BACKEND=bedrock uv run scripts/serve.py
```

That path makes a real, billed call for every question. [Which model
answers](#which-model-answers) has what each mode costs and what happens when
the one you chose is not reachable.

That fifth step needs a document store to search, and the one committed at
`data/corpus.db` is ready as-is — nothing to build, no credentials needed. If
you want to query a corpus of your own instead, see [Building a
corpus](#building-a-corpus). Either way, if the database is ever missing or
empty, the service says so and exits rather than starting empty;
[What has to be in place](#what-has-to-be-in-place) has the exact message.

`--extra models` is required here, unlike elsewhere in the project. It
installs sentence-transformers and torch, which are what embed your query and
rerank the candidates. A plain `uv sync` leaves them out on purpose — ingestion,
the store, and CI have no use for a deep learning stack — but searching
without them is not possible, and the service will not start.

`scripts/fetch_models.py` downloads the two models into `.cache/` ahead of
time, so that cost is an explicit step rather than something the first
`scripts/serve.py` run stalls on silently. Re-running it against a warm
cache downloads nothing. Skip it and `scripts/serve.py` still works — it
fetches whatever is missing itself before it builds the vector index and
binds the socket — it just means the first start is the one that pays for
the download.

**You do not build the index yourself.** There is no `build-index` command to
remember. The index is a copy of embeddings that already live in the database,
so the service builds it at startup when it is missing and rebuilds it when it
disagrees with what the database holds. Deleting `.cache/chroma` is a safe
thing to do; the next start makes it again.

Everything expensive happens before the port is open — the database, the
index, and both models — so the first query is as fast as the hundredth, and a
service that has started is a service that works.

### Open the page

<http://127.0.0.1:8000> serves the browser application. It is a shell for now
— it tells you the service is up and what it is serving from — and the
endpoints below it are where the answers come from. Nothing had to be built
for it to be there.

### Ask it something

```bash
curl -s localhost:8000/search \
  -H 'content-type: application/json' \
  -d '{"query": "What did we decide about the connector lead time?", "limit": 3}'
```

```jsonc
{
  "query": "What did we decide about the connector lead time?",
  "results": [
    {
      "rank": 1,
      "chunk_id": 412,
      "text": "Priya: Where are we on the rev B boards?\nMarcus: Two weeks out, assuming the connectors land. I'll confirm the lead time with Devon before we commit to the date.",
      "document_slug": "rev-b-schedule",
      "source_kind": "transcript",
      "title": "Rev B schedule",
      "document_date": "2026-03-04",
      "author": null,
      "attendees": ["Priya", "Marcus", "Sofia"],
      "location": "turns 0-1",
      "span_start": 0,
      "span_end": 1,
      "topics": ["Hardware", "Supply chain"],
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

### Ask for an answer instead

```bash
curl -s localhost:8000/answer \
  -H 'content-type: application/json' \
  -d '{"question": "What did we decide about the XT-9 rev B thermal drift?"}'
```

```jsonc
{
  "question": "What did we decide about the XT-9 rev B thermal drift?",
  "answer": "The team settled on a two-track response ...",
  "citations": [
    {
      "chunk_id": 98,
      "document_slug": "xt-9-rev-b-thermal-drift-firmware-workaround-feasibility",
      "source_kind": "transcript",
      "title": "XT-9 Rev B Thermal Drift - Firmware Workaround Feasibility",
      "document_date": "2026-03-05",
      "author": null,
      "attendees": ["Marcus", "Sofia", "Devon"],
      "location": "turns 4-13"
    }
    // ...the rest of what it read
  ],
  "searches": 1,
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
comes back as a `200` with no citations, like any other answer.

### Not knowing also suggests who to ask

A decline is a better place to stop than a made-up answer, and still a poor
place to stop. The passages that scored well without settling the question
each name the person who wrote them or the people who were in the room, so
the search that failed already identifies who would know. When the agent
searched and could not answer from what came back, `routing` carries that:

```jsonc
{
  "answer": "The record does not say which Rev B units are installed in high-temperature environments. ...",
  "routing": {
    "candidates": [
      {
        "name": "Sofia",
        "role": "Firmware Engineer",
        "department": "Engineering",
        "passages": 5,
        "evidence": [
          {
            "chunk_id": 214,
            "document_slug": "xt-9-rev-b-thermal-qualification-report",
            "source_kind": "docx",
            "title": "XT-9 Rev B Thermal Qualification Report",
            "document_date": "2026-03-12",
            "author": "Sofia",
            "attendees": [],
            "location": "Recommendation > Rev C Replacement Threshold"
          }
          // ...the rest of what put Sofia here
        ]
      }
      // ...Marcus and Devon, one passage each
    ],
    "question": "I was looking for a list of Rev B units that are deployed in high-temperature settings. The available documentation only mentions the thermal limits for Rev B units and notes that a minority of the approximately 340 field units have documented installation temperatures, but it does not specify which ones are in high-temperature environments. Which of the Rev B units in the field are installed in high-temperature environments?"
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
made — see [Telling it when it is wrong](#telling-it-when-it-is-wrong).

A question the corpus answers gets no routing, and neither does one declined
without a search: the capital of France is not something anyone here should
be asked. Routing is for the questions this organization ought to be able to
answer and the record does not.

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
question. The gaps, corrections, and feedback below go in that same file, and
so does the [trace](#tracing-each-query) of every question.
Deleting it costs you the threads and the records it held and nothing else.
Point `--usage-db` somewhere else to keep it elsewhere.

### Watching it work

A local answer can take tens of seconds, most of it spent waiting on the
model. Ask for `text/event-stream` and the same endpoint reports each step as
it happens, as [server-sent
events](https://html.spec.whatwg.org/multipage/server-sent-events.html), and
sends the answer last:

```bash
curl -sN localhost:8000/answer \
  -H 'content-type: application/json' \
  -H 'accept: text/event-stream' \
  -d '{"question": "What did we decide about the XT-9 rev B thermal drift?"}'
```

```
event: started
data: {"thread_id": "bafccadb164e4447b21f7a8899f11390"}

event: drafting
data: {}

event: searching
data: {"query": "XT-9 rev B thermal drift decision"}

event: searched
data: {"query": "XT-9 rev B thermal drift decision", "citations": [{"chunk_id": 98, ...}, ...]}

event: drafting
data: {}

event: verifying
data: {}

event: verified
data: {"verification": null, "redraft": false}

event: routing
data: {}

event: answer
data: {"question": "What did we decide about the XT-9 rev B thermal drift?", "answer": "The team settled on a two-track response ...", ...}
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

### Which model answers

`/answer` runs on one of two models, and which one is yours to choose:

|            | local (the default)                   | hosted                                                    |
| ---------- | ------------------------------------- | --------------------------------------------------------- |
| model      | `granite4.1:8b`                       | Claude Sonnet 4.6, as `us.anthropic.claude-sonnet-4-6`     |
| served by  | Ollama, on this machine               | Bedrock                                                    |
| needs      | Ollama running, that model pulled     | `AWS_BEARER_TOKEN_BEDROCK` and `AWS_REGION`                |
| costs      | nothing, beyond the laptop's battery  | a billed call per model turn, and a turn that searches makes several |

The local model is the only moving part here that has to be installed
separately:

```bash
brew install ollama && ollama serve &
ollama pull granite4.1:8b      # ~5.3 GB, once
```

It is a small model chosen to fit a 16GB machine, and that shows in the way it
works rather than only in the prose: expect it to pick its tools less surely
than a large hosted one — a question it should have searched for, answered
from memory, or a second search it did not need — and expect an occasional
answer that reads like it was written by a small model. Nothing tunes that
away.

The hosted model needs a Bedrock API key and a region, read from the process
environment or from `.env` — the same file
[`scripts/bedrock_smoke_test.py`](scripts/bedrock_smoke_test.py) and the
corpus scripts read theirs from, and not `.env.admin`, which holds
provisioning settings instead:

```bash
cat >> .env <<'EOF'
AWS_BEARER_TOKEN_BEDROCK=your-bedrock-api-key
AWS_REGION=us-east-1
EOF
```

[docs/provisioning.md](docs/provisioning.md) is where a key comes from and how
the spend is bounded.

#### Choosing one

```bash
uv run scripts/serve.py                                       # local
CORPUS_QUERY_MODEL_BACKEND=bedrock uv run scripts/serve.py    # hosted
```

`CORPUS_QUERY_MODEL_BACKEND` takes `ollama` or `bedrock`, is read from the
environment or from `.env`, and is the only thing that decides. **Having a
Bedrock key does not select Bedrock.** A key sits in `.env` because the corpus
scripts need one, so if both are configured — a key in the file and Ollama
running — the local model answers, and if neither is, the local model is still
what the service reaches for. Whichever is chosen is built before the socket
opens, and the service says which on the way up:

```
/answer is answering from granite4.1:8b on ollama.
```

A value that is neither backend is refused by name rather than guessed at,
because the two differ in what they cost:

```
error: 'bedrok' is not a backend this project has. Set CORPUS_QUERY_MODEL_BACKEND to 'ollama' or 'bedrock', or leave it unset to answer from the local model.
```

So is asking for the hosted model without the settings it needs. Both are a
message and a non-zero exit before anything is served:

```
error: AWS_BEARER_TOKEN_BEDROCK is not set, and answering from bedrock needs it. Add it to .env or export it, or unset CORPUS_QUERY_MODEL_BACKEND to answer from the local model instead.
```

What is *not* checked at startup is whether the model can be reached. Building
either client opens no connection, so a service whose Ollama is not running,
or whose key is no longer good, starts normally and fails on the first
question: `/answer` comes back `500 Internal Server Error`, and the
traceback in the service's log names the cause — `httpx.ConnectError` for an
Ollama that is not listening, the AWS error for a key Bedrock rejects. The
service keeps running, `/search` keeps working, and `/health` still reports
`ok`, since what it checks is the store and the index rather than the model.

#### How the two fit together

The swap is not a base URL or a model name. The two models do not agree on the
wire about how a tool call is asked for or returned, so each arrives through
its own LangChain chat model class — `ChatOllama` and `ChatBedrockConverse` —
and [`corpus_query/agent/model.py`](corpus_query/agent/model.py) is the one
factory that decides which. The graph's nodes name neither: they are handed a
chat model and bind the search tool to it with `bind_tools`, so the tool
schema is written once and translated by whichever class received it. Adding a
third backend is a change to that module and to nothing else.

One difference is deliberate rather than incidental: the hosted model is asked
for non-streamed replies. LangChain's Bedrock Converse model has had trouble
streaming tool calls against cross-region inference profiles, which is exactly
what `us.anthropic.claude-sonnet-4-6` is, and the agent awaits every reply
whole before the graph moves on — so there is nothing to give up by turning
streaming off, and a documented failure mode to avoid.

The corpus scripts are not part of this. Generating and enriching a corpus
calls Bedrock directly through the `anthropic` SDK, they are preprocessing you
run by hand rather than anything a question reaches, and they have no local
path — see [Building a corpus](#building-a-corpus).

### Telling it when it is wrong

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

### The review queue

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

Gaps, corrections, and feedback are also the diagnostic layer underneath the
one metric worth watching in a launch window — see
[docs/retention.md](docs/retention.md).

### Tracing each query

When an answer is bad, the useful question is which step went wrong: retrieval
found nothing, the reranker buried the right passage, or the model ignored what
it was given. Every `/search` and `/answer` is traced with
[OpenTelemetry](https://opentelemetry.io/) so that is something to look up
rather than guess at. An answer's trace holds a span for the run, one for each
model call (the rewrite, each draft, verification, routing), one for each
search the model asked for, and under each search one for embedding the query,
the lexical search, the vector search, fusion, and reranking.

The spans carry the numbers that explain them. A search's span lists the
passages it returned with their rerank scores and where lexical search, vector
search, and fusion had each put them beforehand, alongside the confidence
signals `/search` already reports. A model call's span follows the
[semantic conventions for generative
AI](https://github.com/open-telemetry/semantic-conventions-genai) — provider,
model, token counts, why it stopped — so a tracing backend that knows them
shows them without configuration.

Spans are written to the `spans` table in `data/usage.db`, a few seconds after
they end, so reading a trace is a query:

```bash
sqlite3 data/usage.db "
  SELECT name,
         (end_time_unix_nano - start_time_unix_nano) / 1e6 AS ms,
         json_extract(attributes, '$.\"gen_ai.usage.output_tokens\"') AS tokens
  FROM spans
  WHERE trace_id = (SELECT trace_id FROM spans ORDER BY start_time_unix_nano DESC LIMIT 1)
  ORDER BY start_time_unix_nano"
```

Three environment variables change where they go:

| Variable | Effect |
|---|---|
| `CORPUS_QUERY_TRACE_CONSOLE=1` | Also print each span to standard output as it ends. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Also send spans over OTLP/gRPC to the collector at that address, such as `http://localhost:4317`. The other standard `OTEL_EXPORTER_OTLP_*` settings apply. |
| `OTEL_SDK_DISABLED=true` | Turn tracing off. Nothing is recorded, and answering is otherwise unchanged. |

The last two are OpenTelemetry's own names, so they mean here what they mean
anywhere else.

### Check that it is up

```bash
curl -s localhost:8000/health
```

```json
{
  "status": "ok",
  "database": {"readable": true, "chunks": 1184},
  "index": {"loaded": true, "vectors": 1184}
}
```

Reaching it at all says the application is running. The body says whether the
database still reads and whether the vector index is loaded, each with what it
holds, so an empty corpus is distinguishable from a broken one. If either
stops answering, the status is `degraded` and the response is a `503`.

### What has to be in place

The service needs a document store at `data/corpus.db` holding ingested,
enriched chunks. It needs a vector index too, but as above, that one it builds
for itself.

If the database is missing, or is there but holds no chunks, the service says
so and exits:

```
error: no document store at data/corpus.db. Ingest a corpus first: uv run scripts/ingest.py
```

That is deliberate. A search service with no corpus behind it answers every
question with an empty result list, which looks exactly like a question the
corpus cannot answer — a failure at startup is worth more than a hundred
plausible-looking empty responses.

The database ships with this repository, so a fresh clone already has one at
`data/corpus.db`. Point `--db` elsewhere to use a different store, or build
your own — see [Building a corpus](#building-a-corpus).

`data/usage.db` needs nothing in place. It is created empty the first time
`/answer` is asked something, it is not committed and is gitignored, and it is
the only file the service writes to — running queries never modifies the
corpus.

---

Everything below is for people working on the project. If you only want to run
queries, you can stop here.

## Building a corpus

The corpus in this repository has already been built, and nothing below needs
running to use it. This is how it got there, and what to run if you want a
corpus of your own instead.

```bash
uv run scripts/generate_transcripts.py   # billed; --dry-run prints the prompt
uv run scripts/ingest.py                 # free, offline, deterministic
uv run scripts/enrich.py                 # billed; --dry-run prints the prompts
```

Ingestion reads each document with the reader for its format — a transcript is
split into chunks of whole turns, a Word document into its heading sections, a
deck into one chunk per slide, and a workbook into windows of 10 to 20 rows per
sheet, each rendered as a markdown table with its header repeated — so a
citation can say which section, slide, or row range a claim came from — and
writes documents, attendees, and chunks. With no paths named it reads both
`data/transcripts` and `data/office`. Enrichment adds a summary, topics, a time
sensitivity, a business
impact, and an embedding per chunk. Querying reads what those three leave
behind and calls nothing.

The two billed steps need a Bedrock key; see
[docs/provisioning.md](docs/provisioning.md) for where one comes from and how
the spend is bounded.

A `.doc`, `.ppt`, or `.xls` file is converted to its modern equivalent with
LibreOffice headless before it is read, so the corpus never needs a separate
reader for the legacy binary formats. LibreOffice is optional: the committed
corpus is all modern files, needs none of it, and nothing here requires it to
be installed. It only matters if a legacy file is added to the corpus later,
in which case ingesting it needs LibreOffice on `PATH` or, on macOS, in the
usual place the app installs it.

The Word, PowerPoint, and Excel files in `data/office/` came from three
independent Claude Code sessions running Opus, one per file type. Each session
was told only to read its prompt and follow it exactly:
[docx.md](corpus_query/office/prompts/docx.md),
[pptx.md](corpus_query/office/prompts/pptx.md), or
[xlsx.md](corpus_query/office/prompts/xlsx.md). The prompts build on
[data/office_files_guidance.md](data/office_files_guidance.md), which specifies
the nine documents.

## Development

```bash
uv sync
uv run pytest          # tests
pre-commit run --all-files
```

The embedding and reranking models are an optional extra, because they bring
torch with them and most of the system does not need it:

```bash
uv sync --extra models     # adds sentence-transformers and torch
uv run pytest -m slow      # the tests that load them
```

Anything that embeds or reranks needs that extra installed. Without it those
tests skip and the modules that import them raise on import, which is the
intended signal rather than a failure to diagnose. The API's own tests drive
the application in process over ASGI with retrieval stubbed, so they run
without the extra.

Hooks run ruff, gitleaks, a Conventional Commits check, and — for changes
under `frontend/` — eslint and the TypeScript compiler. Install them once with
`pre-commit install` and `pre-commit install --hook-type commit-msg`. CI runs
the same set.

## The committed frontend

The browser application lives in `frontend/`: React and TypeScript, compiled
by Vite. Its build output is committed, at
`corpus_query/api/static/`, and FastAPI serves that directory at `/`.

Committing a build is unusual enough to say why. Node is a build-time
dependency and nothing more — no part of running this system calls it — so
shipping the build means a clone needs Python and nothing else to get a
working page. The alternative is telling everyone who wants to run the project
to install a second toolchain to produce a file that was identical for
everyone who produced it. The bundle is a couple of hundred kilobytes, which
is a small thing to keep in a repository in exchange for deleting the largest
setup obstacle it had.

The consequence is that **a frontend change is not finished until the build is
rebuilt and committed with it**. The source and the bundle are one change.

```bash
npm --prefix frontend ci       # once
npm --prefix frontend run dev  # http://localhost:5173, against a live API
```

`npm run dev` serves the application itself with hot module replacement and
proxies `/search`, `/answer`, and `/health` through to `scripts/serve.py` on
port 8000, so run that in another terminal. Requests stay same-origin that
way, which is why the API carries no CORS configuration for the sake of
development.

```bash
npm --prefix frontend run lint       # eslint
npm --prefix frontend run typecheck  # tsc
npm --prefix frontend test           # vitest, against a stubbed API
npm --prefix frontend run build      # writes corpus_query/api/static/
```

If `corpus_query/api/static/` is ever missing, the API still starts and the
endpoints still answer; `/` says what to run instead. The page is the one
thing that needs it.

## Provisioning (for the record)

The Bedrock calls above were made by an IAM identity that can invoke one model
and nothing else, under a monthly budget that attaches a deny policy at 100%
of actual spend — so a runaway loop stops rather than keeps billing. No
account id appears anywhere in the repository; the CDK stack builds the ARNs
it grants on from its own account and region tokens.

None of it is needed to run the application, and none of it needs running
again. [docs/provisioning.md](docs/provisioning.md) has the stack, the
settings it reads, and the reasoning behind the narrower choices.
