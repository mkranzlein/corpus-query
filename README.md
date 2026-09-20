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

## Querying needs no AWS account

Search runs entirely on your machine: the committed SQLite database, a local
embedding model, and a local reranking model. **No AWS account, no Bedrock
endpoint, and no API key are involved in answering a query.** Nothing about
`POST /search` reaches a network service, and it costs nothing to run.

Bedrock comes into it one step earlier and for a different job. The
transcripts were generated with a hosted model, and enrichment — the
summaries, topics, and priority assessments that results carry — called one
too. That work is done and its output is in the database. Building a fresh
corpus of your own is the one thing in this repository that needs credentials;
see [Building a corpus](#building-a-corpus).

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

# 3. Start the service.
uv run python -m scripts.serve
```

`--extra models` is required here, unlike elsewhere in the project. It
installs sentence-transformers and torch, which are what embed your query and
rerank the candidates. A plain `uv sync` leaves them out on purpose — ingestion,
the store, and CI have no use for a deep learning stack — but searching
without them is not possible, and the service will not start.

The first `scripts.serve` takes a minute: it downloads the two models into
`.cache/` and builds the vector index. Both are caches, so every later start
is fast.

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
      "subject": "Rev B schedule",
      "meeting_date": "2026-03-04",
      "turn_start": 0,
      "turn_end": 1,
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
error: no document store at data/corpus.db. Ingest a corpus first: uv run python -m scripts.ingest
```

That is deliberate. A search service with no corpus behind it answers every
question with an empty result list, which looks exactly like a question the
corpus cannot answer — a failure at startup is worth more than a hundred
plausible-looking empty responses.

The database is not committed to this repository, so a fresh clone does not
have one. Either use one you were given, at `data/corpus.db` or wherever you
like with `--db`, or build your own.

---

Everything below is for people working on the project. If you only want to run
queries, you can stop here.

## Building a corpus

This is the one part that costs money and needs credentials: transcripts are
generated with a hosted model through Amazon Bedrock's OpenAI-compatible
endpoint, and enrichment calls one several times per document. Settings come
from `.env`: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_PROJECT`.

```bash
uv run python -m scripts.generate_transcripts   # billed; --dry-run prints the prompt
uv run python -m scripts.ingest                 # free, offline, deterministic
uv run python -m scripts.enrich                 # billed; --dry-run prints the prompts
```

Ingestion splits transcripts into chunks of whole turns and writes documents,
attendees, and chunks. Enrichment adds a summary, topics, a time sensitivity,
a business impact, and an embedding per chunk. Querying reads what those three
leave behind and calls nothing.

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

This repository also holds the AWS provisioning behind the Bedrock endpoint:
a Bedrock project that inference is billed to, an IAM policy that permits
inference against that project and nothing else, and a budget alarm. It
documents how the account was set up — it is not something a user of the
application needs to run, or even look at. Querying needs none of it, and
generating a corpus needs only a key that this section explains the origin of.

What follows is a record of the steps that produced the current setup, kept
for anyone who needs to reproduce, audit, or extend the provisioning itself.

### Requirements

- Python 3.14 and [uv](https://docs.astral.sh/uv/)
- The [AWS CDK CLI](https://docs.aws.amazon.com/cdk/v2/guide/cli.html)
  (`npm install -g aws-cdk`), which runs the app through `uv` for you
- AWS credentials for an identity that can create Bedrock projects, IAM
  policies, and budgets
- The target account and region [bootstrapped for
  CDK](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html)
  (`cdk bootstrap`), if they have not been already

### Configuration

Settings live in `.env.admin`, which is gitignored and never committed: the
project ARN it ends up holding contains the account id. Anything exported in
the shell overrides the file.

| Setting | Meaning |
| --- | --- |
| `AWS_REGION` | Region the project and stack live in |
| `AWS_PROJECT_NAME` | Bedrock project name, e.g. `corpus-query` |
| `AWS_PROJECT_TAG` | Value of the `Project` cost-allocation tag |
| `AWS_BUDGET_EMAIL` | Address that budget alerts are sent to |
| `AWS_BUDGET_LIMIT_USD` | Monthly budget in USD (default `20`) |
| `AWS_PROJECT_ARN` | Written by the creation script; do not set by hand |

### The three steps, in order

Each one needs what the previous one produced.

#### 1. Create the Bedrock project

Bedrock's Projects API is REST-only — no CLI command, no SDK client — so this
is a SigV4-signed request rather than a CDK resource:

```bash
uv run python -m infra.create_project --dry-run  # print the request, send nothing
uv run python -m infra.create_project            # create it
```

The script prints the new project's ARN and id, and writes `AWS_PROJECT_ARN`
into `.env.admin`. Creating a project needs admin credentials; a long-term
Bedrock API key can only get and list projects.

#### 2. Deploy the stack

The stack reads `AWS_PROJECT_ARN` from `.env.admin`, so it will not
synthesize before step 1 has run.

```bash
cdk synth
cdk deploy
```

It creates a customer-managed IAM policy allowing
`bedrock-mantle:CreateInference` on that project ARN alone, and a monthly cost
budget that alerts at 80% of actual spend and at a forecast of 100%. The
policy's ARN is a stack output.

#### 3. Mint the API key

Attach the policy from step 2 to the identity the key belongs to, then create
the Bedrock API key in the console or with the CLI, and hand it over out of
band.

The key is deliberately not created by CloudFormation: its value would be
stored in stack state and in stack outputs, readable by anyone who can
describe the stack.

### Notes

- The SigV4 signing service name (`bedrock-mantle`) is confirmed against a
  live call: the project creation script ran successfully against the real
  endpoint, which also validated the request body shape and the response
  field names.
- The budget covers account spend rather than filtering on the `Project` tag.
  Tag-scoped filtering needs the cost allocation tag to be activated in
  Billing, which is console-only; account-wide is what catches runaway spend
  either way.
