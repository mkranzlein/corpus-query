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

An interface a person would sit in front of is deliberately not here yet.
Until then, `curl` is the interface.

Everything runs on your machine: a SQLite document store on disk, a local
embedding model, a local reranking model, and a local chat model served by
Ollama. **No AWS account, no Bedrock endpoint, and no API key are involved in
answering a query.** A hosted model wrote the transcripts and enriched them,
but that work is done and its output ships in the database. Building a corpus
of your own is the one thing here that needs credentials; see [Building a
corpus](#building-a-corpus).

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
```

Step 4 is only needed for `/answer`. `/search` ranks without a chat model, and
the service starts either way — a question asked of `/answer` with no Ollama
running is the one thing that fails.

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
  "thread_id": "bafccadb164e4447b21f7a8899f11390"
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
It is text to edit. Nothing is sent anywhere, nothing is recorded, and the
suggestion is gone when the response is.

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
question. Deleting it costs you the threads it held and nothing else. Point
`--usage-db` somewhere else to keep it elsewhere.

The chat model is `granite4.1:8b`, served locally by Ollama, and it is the
only moving part here that has to be installed separately. It is a small model
chosen to fit a 16GB machine: expect it to pick its tools less surely than a
large one, and expect an occasional answer that reads like it was written by a
small model. Nothing about `/answer` calls a hosted model or costs anything.

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

Hooks run ruff, gitleaks, and a Conventional Commits check. Install them once
with `pre-commit install` and `pre-commit install --hook-type commit-msg`.

## Provisioning (for the record)

The Bedrock calls above were made by an IAM identity that can invoke one model
and nothing else, under a monthly budget that attaches a deny policy at 100%
of actual spend — so a runaway loop stops rather than keeps billing. No
account id appears anywhere in the repository; the CDK stack builds the ARNs
it grants on from its own account and region tokens.

None of it is needed to run the application, and none of it needs running
again. [docs/provisioning.md](docs/provisioning.md) has the stack, the
settings it reads, and the reasoning behind the narrower choices.
