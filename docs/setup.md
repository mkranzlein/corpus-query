# Setting up and tearing down

Everything it takes to go from a fresh clone to an answer from `/answer`, on
macOS or on Ubuntu, and everything it takes to go back again. The
[Quickstart](../README.md#quickstart) in the README is the short version of
the same path.

Two backends can answer a question, and the setup differs only in one step:

- **Local**, the default. A chat model served by Ollama on this machine.
  Nothing is billed and no account is needed.
- **Bedrock**. A hosted model, called with a Bedrock API key you are given
  separately. Every question is a billed call. See [Which model
  answers](../README.md#which-model-answers) for what each one costs.

Searching needs neither: `/search` runs on the local embedding and reranking
models alone.

Other Linux distributions are not covered step by step. Install uv and Ollama
the way their own documentation says for your distribution —
[uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Ollama](https://docs.ollama.com/linux) — and the rest of this page applies
unchanged.

## 1. Install the tools

### macOS

Ollama needs macOS 14 (Sonoma) or newer.

```bash
# git, if `git --version` says it is missing. This installs Apple's
# command line developer tools, which include it.
xcode-select --install

# uv, which manages the Python version and the dependencies. Open a new
# terminal afterwards so that `uv` is on your PATH.
curl -LsSf https://astral.sh/uv/install.sh | sh

# Ollama, only for the local backend. Installs Ollama.app into
# /Applications, links the `ollama` command into /usr/local/bin, and starts
# the app.
curl -fsSL https://ollama.com/install.sh | sh
```

Ollama can also be installed by downloading `Ollama.dmg` from
<https://ollama.com/download/mac> and dragging the app into Applications,
which is the method Ollama's own macOS page prefers. Either way the same app
ends up in the same place, so the teardown below is the same. Open the app
once if you installed it that way; it offers to link the `ollama` command on
first start.

### Ubuntu

```bash
# curl and git, and zstd, which Ollama's installer needs to unpack its
# download. A desktop install of Ubuntu does not always have all three.
sudo apt update
sudo apt install curl git zstd

# uv, which manages the Python version and the dependencies. Open a new
# terminal afterwards so that `uv` is on your PATH.
curl -LsSf https://astral.sh/uv/install.sh | sh

# Ollama, only for the local backend. Installs the `ollama` command, creates
# an `ollama` system user, and registers and starts an `ollama` systemd
# service that also starts on boot.
curl -fsSL https://ollama.com/install.sh | sh
```

To check that the Ollama service is up:

```bash
sudo systemctl status ollama
```

On Linux the project installs the CPU-only build of torch, which is all it
uses. No GPU or GPU driver is needed.

## 2. Install the project

The same on both:

```bash
git clone https://github.com/mkranzlein/corpus-query.git
cd corpus-query

# The project and its model stack. uv downloads Python 3.14 first if this
# machine does not have it.
uv sync --extra models

# The embedding and reranking weights, into .cache/huggingface (~215 MB, once).
uv run scripts/fetch_models.py
```

Every command from here on runs from the root of the clone.

## 3. Choose a backend

### Local, with Ollama

Ollama has to be running, which it is after the install above:

```bash
ollama pull granite4.1:8b     # ~5.3 GB, once
```

### Bedrock

Skip Ollama entirely. The Bedrock settings live in a `.env` file at the root
of the clone, which is gitignored and never committed. If you were given a
`.env`, put it there. Otherwise start from the template the repository
ships, which has every setting the service reads from that file and no
values for the secret ones:

```bash
cp -n .env.example .env   # -n leaves an existing .env alone
```

Then fill in:

| Setting | What it is |
| --- | --- |
| `AWS_BEARER_TOKEN_BEDROCK` | A Bedrock API key. [docs/provisioning.md](provisioning.md) is where one comes from. |
| `AWS_REGION` | The region to call Bedrock in. The model is a US cross-region inference profile, so use a US region such as `us-east-1`. |
| `CORPUS_QUERY_MODEL_BACKEND` | Optional. `bedrock` here makes every start answer from Bedrock; leave it out to choose per start, as below. |

A key in `.env` does not by itself select Bedrock. Only
`CORPUS_QUERY_MODEL_BACKEND` does, so that a key kept there for other reasons
never turns a free question into a billed one.

## 4. Start it and ask something

```bash
uv run scripts/serve.py                                      # local
CORPUS_QUERY_MODEL_BACKEND=bedrock uv run scripts/serve.py   # Bedrock
```

On the way up it prints which model `/answer` is answering from. The committed
corpus at `data/corpus.db` is what it serves, so there is nothing to build.
When it says it is running, open <http://127.0.0.1:8000>, or from another
terminal:

```bash
curl -s localhost:8000/answer \
  -H 'content-type: application/json' \
  -d '{"question": "What did we decide about the RV-2 introductory price?"}'
```

The service stays in the foreground of the terminal it was started in, and
that terminal's output is its log.

## Teardown

What running this project leaves on a machine, where each item came from, and
whether it is worth keeping:

| Item | Where | Safe to keep? |
| --- | --- | --- |
| The pulled chat model | Ollama's model store: `~/.ollama/models` on macOS, `/usr/share/ollama/.ollama/models` on Ubuntu | Yes. ~5.3 GB, and any other project on this machine that uses `granite4.1:8b` shares the same copy. |
| Ollama itself | See below | Yes, if anything else uses it. |
| Embedding and reranking weights, and the vector index | `.cache/` in the clone (`huggingface/` and `chroma/`) | Yes. Both are rebuilt when missing: the weights by downloading ~215 MB again, the index at the next start. |
| Recorded usage | `data/usage.db` in the clone, with `-wal` and `-shm` files beside it while the service runs | Only if you want what it holds: the conversation history, the gaps, corrections, and feedback recorded against answers, and each question's trace. Removing it loses those; the service makes a new, empty one when next asked something. |
| The project environment | `.venv/` in the clone | Yes. `uv sync --extra models` makes it again. |
| Bedrock credentials | `.env` in the clone | Not once you are done with Bedrock. It holds a working API key. |
| uv, its cache, and the Python it downloaded | See below | Yes. They are shared with every other project that uses uv. |

`data/corpus.db` is not on this list. It is part of the repository rather than
something running the project produced, and the service will not start
without it.

If `HF_HOME` was already set in your environment when you ran the project, the
weights went to that directory instead of `.cache/huggingface`, alongside
whatever else uses it, and are best left there.

### 1. Stop the service

Press Ctrl+C in the terminal running `scripts/serve.py`. It prints `Press
CTRL+C to quit` when it starts, and nothing else it started keeps running.

### 2. Remove the pulled model

`ollama rm` asks the running Ollama server to delete the model, so do this
before stopping Ollama. It is the same on both:

```bash
ollama rm granite4.1:8b
```

### 3. Stop Ollama

On macOS, quit Ollama from its icon in the menu bar.

On Ubuntu, Ollama runs as a systemd service. Stop it, and keep it from
starting again at boot:

```bash
sudo systemctl stop ollama
sudo systemctl disable ollama
```

`sudo systemctl enable --now ollama` undoes both.

### 4. Remove what the project wrote in the clone

The same on both, from the root of the clone, after the service has stopped:

```bash
rm -rf .cache                                          # weights and vector index
rm -f data/usage.db data/usage.db-wal data/usage.db-shm  # recorded usage
rm -rf .venv                                           # the project environment
rm -f .env                                             # Bedrock credentials
```

Deleting `.env` removes the key from this machine but does not revoke it,
and anyone else who has a copy can still use it. Revoking it is done in AWS:
see [Handle compromised long-term and short-term Amazon Bedrock API
keys](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-revoke.html).

If you are finished with the clone as a whole, deleting its directory removes
all of the above at once.

### 5. Optionally, uninstall Ollama

Only if nothing else on this machine uses it. This also removes every model
Ollama holds, not just this project's.

On macOS:

```bash
sudo rm -rf /Applications/Ollama.app
sudo rm /usr/local/bin/ollama
rm -rf ~/"Library/Application Support/Ollama"
rm -rf ~/"Library/Saved Application State/com.electron.ollama.savedState"
rm -rf ~/Library/Caches/com.electron.ollama/
rm -rf ~/Library/Caches/ollama
rm -rf ~/Library/WebKit/com.electron.ollama
rm -rf ~/.ollama
```

If you installed Ollama with Homebrew instead, `brew uninstall ollama` removes
the program, after `brew services stop ollama` if you had started it as a
service. Its models are still in `~/.ollama`, so remove that as above if you
want them gone too.

On Ubuntu, after stopping and disabling the service in step 3:

```bash
sudo rm /etc/systemd/system/ollama.service
sudo systemctl daemon-reload
sudo rm -r $(which ollama | tr 'bin' 'lib')   # its libraries, beside the binary
sudo rm $(which ollama)
sudo userdel ollama
sudo groupdel ollama
sudo rm -r /usr/share/ollama                  # includes every pulled model
```

The libraries line has to run before the binary is removed, because it finds
them from where the binary is.

### 6. Optionally, uninstall uv

Only if nothing else on this machine uses it. The first three lines remove
uv's data for every project, not just this one: its cache, every Python
version it downloaded, and every tool installed with `uv tool`. The same on
both:

```bash
uv cache clean
rm -r "$(uv python dir)"
rm -r "$(uv tool dir)"
rm ~/.local/bin/uv ~/.local/bin/uvx
```

The installer also added a line to your shell's startup files that puts
`~/.local/bin` on your PATH, and left a small `~/.local/bin/env` script for
that line to run. uv's uninstall steps do not mention either. Both are
harmless with uv gone; remove them by hand if you want them gone too.

If you installed uv with Homebrew instead, `brew uninstall uv` replaces the
last line.

The packages `apt` installed on Ubuntu in step 1 — curl, git, and zstd — are
general-purpose tools that other software relies on. Leave them.
