# corpus-query

[![codecov](https://codecov.io/gh/mkranzlein/corpus-query/graph/badge.svg?token=ZGULR6SXPA)](https://codecov.io/gh/mkranzlein/corpus-query)

Ask a corpus of meeting transcripts a question in plain English and get back
the passages that bear on it. Each result carries where it came from — the
meeting, its date, the turns the passage spans — and the metadata derived from
it during ingestion: the topics the meeting was filed under, how time
sensitive it is, how much business impact it carries. Alongside the results
come confidence signals about them.

It returns passages, not prose. There is no summary at the end, and nothing
here writes a sentence that was not spoken in a meeting.

## Where this sits

The query API is what exists today: one HTTP endpoint over hybrid retrieval —
BM25 and vector search, fused, then reranked by a cross-encoder — plus the
ingestion and enrichment that fill the corpus it searches.

Two things are deliberately not here yet. An agent that reads these passages
and synthesizes an answer out of them, with citations back to the chunks it
used, is later work; it will be a caller of this endpoint rather than a
replacement for it, which is why the response carries the confidence signals
even though nothing weighs them yet. An interface a person would sit in front
of is later work too. Until then, `curl` is the interface.

Search runs entirely on your machine: a SQLite document store on disk, a local
embedding model, and a local reranking model. **No AWS account, no Bedrock
endpoint, and no API key are involved in answering a query.** A hosted model
wrote the transcripts and enriched them, but that work is done and its output
ships in the database. Building a corpus of your own is the one thing here
that needs credentials; see [Building a corpus](#building-a-corpus).

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

# 4. Start the service. The committed corpus at data/corpus.db is ready to query.
uv run scripts/serve.py
```

That fourth step needs a document store to search, and the one committed at
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
split into chunks of whole turns, a Word document into its heading sections,
so a citation can say which section a claim came from — and writes documents,
attendees, and chunks. With no paths named it reads both `data/transcripts`
and `data/office`. Enrichment adds a summary, topics, a time sensitivity, a business
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
