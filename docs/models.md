# Which model answers

`/answer` runs on one of two models, and which one is yours to choose:

|            | local (the default)                   | hosted                                                    |
| ---------- | ------------------------------------- | --------------------------------------------------------- |
| model      | `granite4.1:8b`                       | Claude Sonnet 4.6, as `us.anthropic.claude-sonnet-4-6`     |
| served by  | Ollama, on this machine               | Bedrock                                                    |
| needs      | Ollama running, that model pulled     | `AWS_BEARER_TOKEN_BEDROCK` and `AWS_REGION`                |
| costs      | nothing, beyond the laptop's battery  | a billed call per model turn, and a turn that searches makes several |

The local model is the only moving part here that has to be installed
separately. [docs/setup.md](setup.md#1-install-the-tools) installs
Ollama on macOS and on Ubuntu; with it running, pull the model:

```bash
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
[`scripts/bedrock_smoke_test.py`](../scripts/bedrock_smoke_test.py) and the
corpus scripts read theirs from, and not `.env.admin`, which holds
provisioning settings instead. [`.env.example`](../.env.example) is a
template with every setting that file takes, and no values for the secret
ones:

```bash
cp -n .env.example .env   # -n leaves an existing .env alone
```

Then fill in `AWS_BEARER_TOKEN_BEDROCK` and `AWS_REGION`;
[docs/setup.md](setup.md#bedrock) says what each one is.
[docs/provisioning.md](provisioning.md) is where a key comes from and how
the spend is bounded.

## Choosing one

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

## How the two fit together

The swap is not a base URL or a model name. The two models do not agree on the
wire about how a tool call is asked for or returned, so each arrives through
its own LangChain chat model class — `ChatOllama` and `ChatBedrockConverse` —
and [`corpus_query/agent/model.py`](../corpus_query/agent/model.py) is the one
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
path — see [Building a corpus](corpus.md).
