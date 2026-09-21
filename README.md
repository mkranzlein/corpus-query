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
add up to, and it says so when they add up to nothing. It posts to `/search`
like any other client, so the two can be asked the same question and compared.
A browser page at `/`, served by the same process, asks `/answer` for you.

What the corpus could not answer is kept. A question the record does not
settle is written down as a gap without anybody filing it, and corrections and
feedback record what a person has to say about an answer.

Answers come from Claude on Bedrock, reached with the credentials in a `.env`
file at the root of the clone, or from a local model served by Ollama if you
would rather keep everything on your machine — see [Which model
answers](#which-model-answers). Retrieval always runs locally: a SQLite
document store on disk, a local embedding model, and a local reranking model,
so **`/search` needs no credentials at all**. A hosted model wrote the
transcripts and enriched them, but that work is done and its output ships in
the database.

## Quickstart

Starting from nothing, on macOS or Ubuntu. [docs/setup.md](docs/setup.md)
has every step for each of them, including installing uv, answering from a
local model instead, and a [teardown](docs/setup.md#teardown) that stops
everything and removes what was downloaded and written.

```bash
# 1. Install uv: see docs/setup.md for the command on macOS and on Ubuntu.

# 2. Install the project, with the model stack.
git clone https://github.com/mkranzlein/corpus-query.git
cd corpus-query
uv sync --extra models
```

> [!IMPORTANT]
> **3. Put your `.env` in the clone.** The `.env` you were given holds the
> credentials that let `/answer` run inference on Bedrock. It goes at the
> root of the clone — the `corpus-query` directory you just changed into,
> next to this README:
>
> ```bash
> cp /path/to/your/.env .env
> ```
>
> No `.env`, or rather run inference on your own machine? See [Answering
> from a local model instead](#answering-from-a-local-model-instead), just
> below.

```bash
# 4. Fetch the embedding and reranking weights (~215 MB, once).
uv run scripts/fetch_models.py

# 5. Start the service, answering from Bedrock. The committed corpus at
#    data/corpus.db is ready to query.
CORPUS_QUERY_MODEL_BACKEND=bedrock uv run scripts/serve.py
# The page is at http://127.0.0.1:8000, the endpoints are below it.
# Ctrl+C stops it.
```

Note what is not in that list: Node. The browser application is built ahead of
time and the build is committed, so running the whole system takes Python and
nothing else. See [The committed
frontend](docs/frontend.md).

The service reads the `.env` at startup, and `CORPUS_QUERY_MODEL_BACKEND=bedrock`
is what points `/answer` at Bedrock. `/search` needs neither: it ranks without
a chat model, so the service starts and searches even with no `.env` at all.

### Answering from a local model instead

To keep everything on your machine, `/answer` can run on `granite4.1:8b`
served by Ollama. There is no `.env` to put in place for this; install Ollama
instead ([docs/setup.md](docs/setup.md#1-install-the-tools) has the commands
for each OS), then pull the model and start the service without the variable:

```bash
ollama pull granite4.1:8b      # ~5.3 GB, once; Ollama must be running
uv run scripts/serve.py
```

It is a small model, and on a machine without a GPU for Ollama to use it
answers slowly. [Which model answers](#which-model-answers) compares the two,
and [docs/models.md](docs/models.md) has what happens when the one you chose is
not reachable.

The corpus committed at `data/corpus.db` is ready as-is, and the service builds
its vector index itself at startup, so there is nothing to build first. If the
database is ever missing or empty, the service says so and exits rather than
starting empty. [docs/running.md](docs/running.md) has what each step above is
for, what the service does before it opens the port, and what it writes.

## Using it

### Open the page

<http://127.0.0.1:8000> serves the browser application. Type a question and
it is sent to `/answer` as a stream, so each step shows as it happens: what was
searched for, how many passages came back, whether the claims held up. The
answer follows, with every passage it rests on listed under it — the source
file, the author or the people in the room, where in the document it sits, and
the topics, time sensitivity, and business impact derived for it. Each one
opens to the passage itself. A question the record does not settle says so, as
an answer rather than an error. Follow-up questions continue the same
conversation until you start a new one.

Attribution is per passage, not per sentence: the answer is prose, and nothing
in it marks which sentence came from which passage. The page calls the
endpoints below, and anything it does can be done with `curl` too.
[docs/api.md](docs/api.md) covers each of them in full, and interactive API
documentation is at <http://localhost:8000/docs>.

### Search

```bash
curl -s localhost:8000/search \
  -H 'content-type: application/json' \
  -d '{"query": "What is the lead time on the PM-4?", "limit": 3}'
```

Results come back ranked, each carrying its document, date, where in the
document it sits, and the topics, time sensitivity, and business impact
derived for it, alongside confidence signals about the set. A question the
corpus has nothing to say about is a `200` with an empty `results` list.
[docs/api.md](docs/api.md#ask-it-something) has a full response and what
each signal means.

### Ask for an answer

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

The agent decides whether to search and how many times, and `searches` says
what it chose. When the passages do not settle the question it says so, with
`abstained` set to `true`, and `routing` suggests who in the organization would
know. Send `thread_id` back with the next question to follow up, and ask for
`text/event-stream` to watch each step as it happens.
[docs/api.md](docs/api.md) has all of it:
[who to ask](docs/api.md#not-knowing-also-suggests-who-to-ask),
[conversations](docs/api.md#conversations), and
[streaming](docs/api.md#watching-it-work).

### Tell it when it is wrong

Every answer's `answer_id` is what a correction or feedback is recorded
against:

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

A correction can also be typed into the conversation as the next message, and
the agent records it without searching. Gaps, the questions the record did not
settle, are recorded without anyone filing them. `GET /gaps`, `/corrections`,
and `/feedback` read each back, newest first.
[docs/feedback.md](docs/feedback.md) has the three kinds of record and why
they are kept apart.

### The review queue

<http://localhost:8000/review> lists gaps, corrections, and feedback together,
newest first, for someone looking through what the system got wrong. Each row
opens to the full record and can be marked reviewed. Corrections are recorded,
not applied: nothing feeds them back into answers.
[docs/feedback.md](docs/feedback.md#the-review-queue) says why.

### Which model answers

`/answer` runs on one of two models, and which one is yours to choose:

|            | Bedrock (recommended)                                  | local                                  |
| ---------- | ------------------------------------------------------ | -------------------------------------- |
| model      | Claude Sonnet 4.6, as `us.anthropic.claude-sonnet-4-6` | `granite4.1:8b`                        |
| served by  | Bedrock                                                | Ollama, on this machine                |
| needs      | `AWS_BEARER_TOKEN_BEDROCK` and `AWS_REGION`, in `.env` | Ollama running, that model pulled      |
| chosen by  | `CORPUS_QUERY_MODEL_BACKEND=bedrock`                   | leaving `CORPUS_QUERY_MODEL_BACKEND` unset |

```bash
CORPUS_QUERY_MODEL_BACKEND=bedrock uv run scripts/serve.py    # Bedrock
uv run scripts/serve.py                                       # local
```

`CORPUS_QUERY_MODEL_BACKEND` is the only thing that decides. **Having a
Bedrock key in `.env` does not select Bedrock on its own**: name it when you
start the service, as above, or add `CORPUS_QUERY_MODEL_BACKEND=bedrock` to
`.env` to make it the choice on every start. Left unset, the service answers
from the local model. [docs/setup.md](docs/setup.md#bedrock) sets up Bedrock, and [docs/models.md](docs/models.md) has the rest: what
the service checks at startup, what happens when the model cannot be reached,
and how the two backends fit into one agent.

### Tracing and answer quality

Every `/search` and `/answer` is traced with
[OpenTelemetry](https://opentelemetry.io/), into the `spans` table of
`data/usage.db`, so a bad answer can be traced to the step that went wrong;
see [docs/tracing.md](docs/tracing.md). Each answer also records a handful of
numbers for watching quality over time, read with the queries in
[docs/answer-metrics.md](docs/answer-metrics.md).

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

---

Everything below is for people working on the project. If you only want to run
queries, you can stop here.

## Building a corpus

The corpus in this repository has already been built, and nothing needs
running to use it. To build one of your own:

```bash
uv run scripts/generate_transcripts.py   # billed; --dry-run prints the prompt
uv run scripts/ingest.py                 # free, offline, deterministic
uv run scripts/enrich.py                 # billed; --dry-run prints the prompts
```

The two billed steps need a Bedrock key. [docs/corpus.md](docs/corpus.md) has
what each step does, how the office documents were written, and how the
invented names were checked.

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

The browser application's source is in `frontend/` (React and TypeScript,
compiled by Vite), and its build is committed at `corpus_query/api/static/`,
so running the system needs Python and nothing else. **A frontend change is
not finished until the build is rebuilt and committed with it.**
[docs/frontend.md](docs/frontend.md) has why, and the commands for the dev
server, tests, and build.

## Documentation

- [docs/setup.md](docs/setup.md) — setup on macOS and Ubuntu for both
  backends, and [teardown](docs/setup.md#teardown)
- [docs/running.md](docs/running.md) — what the service needs and does at
  startup
- [docs/api.md](docs/api.md) — `/search`, `/answer`, routing, conversations,
  and streaming
- [docs/feedback.md](docs/feedback.md) — gaps, corrections, feedback, and the
  review queue
- [docs/models.md](docs/models.md) — the local and hosted models
- [docs/tracing.md](docs/tracing.md) — per-query traces
- [docs/answer-metrics.md](docs/answer-metrics.md) — answer quality over time
- [docs/retention.md](docs/retention.md) — the metric to watch after launch
- [docs/corpus.md](docs/corpus.md) — building a corpus
- [docs/planted-imperfections.md](docs/planted-imperfections.md) — the flaws
  the corpus was given on purpose, and where they are
- [docs/frontend.md](docs/frontend.md) — the committed frontend build
- [docs/provisioning.md](docs/provisioning.md) — the AWS setup behind the
  Bedrock calls
