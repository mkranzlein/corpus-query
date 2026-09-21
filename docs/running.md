# Running the service

What `scripts/serve.py` needs, what it does before it takes a question, and
what it writes. The [Quickstart](../README.md#quickstart) and
[docs/setup.md](setup.md) have the steps; this is what is behind them.

## What the steps are for

`--extra models` is required to run the service, unlike elsewhere in the
project. It installs sentence-transformers and torch, which are what embed
your query and rerank the candidates. A plain `uv sync` leaves them out on
purpose — ingestion, the store, and CI have no use for a deep learning
stack — but searching without them is not possible, and the service will not
start.

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

## What has to be in place

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
your own — see [Building a corpus](corpus.md).

`data/usage.db` needs nothing in place. It is created empty the first time
`/answer` is asked something, it is not committed and is gitignored, and it is
the only file the service writes to — running queries never modifies the
corpus.
