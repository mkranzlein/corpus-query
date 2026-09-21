"""The one place the agent's chat model is named.

The graph asks for a chat model and gets LangChain's
:class:`~langchain_core.language_models.chat_models.BaseChatModel` back. No
node names a provider, imports a client, or knows what is answering it, which
is what lets a second backend live here and nowhere else.

There are two backends, and they are not one client with a different base URL.
The local one is ``granite4.1:8b`` served by Ollama; the hosted one is Claude
Sonnet 4.6 on Bedrock, reached through the Converse API. The two do not agree
on the wire about how a tool call is asked for or returned, so each arrives
through its own LangChain chat model class — :class:`ChatOllama` and
:class:`ChatBedrockConverse` — and the graph binds its tools to whichever came
back. The tool schema is written once, in
:mod:`corpus_query.agent.retrieval`, and translated by the class that
receives it.

The local backend is the default, deliberately. The tests and an ordinary run
of the service cost nothing and call nothing hosted; answering from Bedrock is
something a user asks for by setting :data:`BACKEND_VARIABLE`, and having a
Bedrock key sitting in ``.env`` is not that request. What the local model
costs instead is reliability: it was chosen to fit a 16GB machine — Apache
2.0, about 5.3GB quantized, trained for function calling — and a model that
size chooses its tools less surely than a large hosted one does. That is
expected here rather than tuned away.

The scripts that generate and enrich the corpus are not part of this. They
call Bedrock directly through the ``anthropic`` SDK, they are preprocessing
run by hand rather than anything a question reaches, and they have no local
path.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

#: The local backend: a model served by Ollama on this machine.
OLLAMA = "ollama"

#: The hosted backend: a model served by Bedrock, which is billed per call.
BEDROCK = "bedrock"

#: What the user sets to choose a backend, in the environment or in ``.env``.
#: Anything else is rejected by name rather than quietly falling back.
BACKEND_VARIABLE = "CORPUS_QUERY_MODEL_BACKEND"

#: Which backend answers when nothing says otherwise. Local, so that a run
#: nobody configured is a run that bills nothing.
DEFAULT_BACKEND = OLLAMA

#: Where the Bedrock settings are read from when the process environment does
#: not already carry them. Deliberately ``.env`` rather than ``.env.admin``:
#: that file holds AWS provisioning settings, this one holds the inference
#: client's, which is the split the corpus scripts already use.
ENV_FILE = ".env"

#: The local model the agent answers from, as Ollama names it. Pull it with
#: ``ollama pull granite4.1:8b``.
DEFAULT_MODEL = "granite4.1:8b"

#: The hosted model, as the US cross-region inference profile for Claude
#: Sonnet 4.6 — which is how the model is offered rather than as a plain
#: foundation-model id: a call is routed to whichever US region has capacity.
#: The corpus scripts name the same profile.
BEDROCK_MODEL = "us.anthropic.claude-sonnet-4-6"

#: Answering from retrieved passages is not a creative task, and a small
#: model left free to wander is a small model inventing a date.
DEFAULT_TEMPERATURE = 0.0

#: How large a context window to ask Ollama for.
#:
#: This has to be set, and it has to be set here. Ollama defaults to a 4096
#: token window regardless of what the model supports, and it makes room by
#: dropping tokens from the front — which is where the system prompt is. Five
#: retrieved passages are enough to go over, so the instructions that say to
#: abstain are the first thing evicted, precisely when they matter most. What
#: that looks like from outside is an agent that follows its prompt on short
#: questions and summarizes whatever retrieval returned on long ones.
#:
#: The size is measured rather than guessed. Ollama reports what it actually
#: evaluated, and the longest realistic turns come in at about 4k tokens for a
#: two-part question that searched twice, and about 5.5k for one search over
#: dense spreadsheet rows — so the default window was missing by a few hundred
#: tokens, which is why the failure looked so arbitrary. 16k is three times
#: the worst turn measured and still leaves room for a conversation to grow on
#: one thread, while costing meaningfully less KV cache than 32k on a machine
#: that has to hold the weights too: 8.2GB resident rather than 10GB.
#:
#: What it does not cover is a turn that runs all the way to
#: :data:`corpus_query.agent.graph.MAX_SEARCHES`. Six searches over passages
#: as dense as the spreadsheet rows would come to roughly 27k tokens, and
#: Ollama would start dropping the front of them again. Real questions take
#: one or two searches and the ceiling exists to stop a loop rather than to be
#: reached, so this is a bound worth knowing rather than one worth sizing the
#: window for.
#:
#: Bedrock has no equivalent setting. The hosted model's window is the
#: model's own and is not something a caller sizes, so this applies to the
#: local backend alone.
DEFAULT_CONTEXT_WINDOW = 16384

#: How long an answer the hosted model may write. Bedrock requires a ceiling
#: where Ollama does not, and an answer out of five passages with its
#: citations is comfortably inside this one.
BEDROCK_MAX_TOKENS = 4096


class ModelConfigurationError(Exception):
    """The chosen backend cannot be built from the settings it was given."""


def load_chat_model(
    backend: str | None = None,
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    context_window: int = DEFAULT_CONTEXT_WINDOW,
    env: Mapping[str, str] | None = None,
) -> BaseChatModel:
    """Build the chat model the agent runs on.

    Args:
        backend: Which backend to answer from, :data:`OLLAMA` or
            :data:`BEDROCK`. Read from :data:`BACKEND_VARIABLE` when it is
            not given, and :data:`DEFAULT_BACKEND` when that is not set
            either.
        model: Which model to answer from, as its own backend names it.
            Defaults to that backend's model.
        temperature: How much the model is allowed to wander. Sent to both
            backends.
        context_window: How many tokens to give the model to work in.
            Ollama only; see :data:`DEFAULT_CONTEXT_WINDOW`.
        env: Settings to read the backend and the Bedrock credentials from.
            Read from the process environment and ``.env`` when not given —
            when the agent is opened, rather than when this module is
            imported.

    Returns:
        The chat model, as LangChain's interface to it.

    Raises:
        ModelConfigurationError: If the named backend is not one this
            project has, or if the one chosen is missing a setting it
            cannot be built without.
    """
    settings = env if env is not None else _environment()
    chosen = selected_backend(backend, settings)
    if chosen == OLLAMA:
        return _local_model(model or DEFAULT_MODEL, temperature, context_window)
    return _hosted_model(model or BEDROCK_MODEL, temperature, settings)


def selected_backend(
    backend: str | None = None, env: Mapping[str, str] | None = None
) -> str:
    """Return which backend answers, without building anything.

    Args:
        backend: The backend asked for outright, if one was.
        env: Settings to read :data:`BACKEND_VARIABLE` from. Read from the
            process environment and ``.env`` when not given.

    Returns:
        :data:`OLLAMA` or :data:`BEDROCK`. Spelling and surrounding
        whitespace are forgiven; an empty value is treated as unset.

    Raises:
        ModelConfigurationError: If what was asked for is not a backend
            this project has. A typo answers from nothing rather than
            silently from the wrong model — and since the two differ in
            what they cost, guessing is the wrong thing to do.
    """
    settings = env if env is not None else _environment()
    asked = backend if backend is not None else settings.get(BACKEND_VARIABLE, "")
    chosen = asked.strip().lower() or DEFAULT_BACKEND
    if chosen in (OLLAMA, BEDROCK):
        return chosen
    raise ModelConfigurationError(
        f"{asked.strip()!r} is not a backend this project has. Set "
        f"{BACKEND_VARIABLE} to {OLLAMA!r} or {BEDROCK!r}, or leave it unset "
        f"to answer from the local model."
    )


def _local_model(model: str, temperature: float, context_window: int) -> BaseChatModel:
    """Build the local model, served by Ollama.

    Args:
        model: Which model to answer from, as Ollama names it.
        temperature: How much the model is allowed to wander.
        context_window: How many tokens to give the model to work in.

    Returns:
        The chat model. Nothing is called here — a server that is not
        running is discovered on the first question, not now.
    """
    from langchain_ollama import ChatOllama

    return ChatOllama(model=model, temperature=temperature, num_ctx=context_window)


def _hosted_model(
    model: str, temperature: float, settings: Mapping[str, str]
) -> BaseChatModel:
    """Build the hosted model, served by Bedrock.

    Streaming is turned off rather than left to the default. LangChain's
    Bedrock Converse model has had trouble streaming tool calls against
    cross-region inference profiles, which is exactly the kind of model id
    :data:`BEDROCK_MODEL` is, and this agent has no use for a streamed
    reply: every model call it makes is awaited whole before the graph moves
    on. Giving up what is not used to avoid the failure mode that is
    documented is the conservative trade.

    Args:
        model: Which model to answer from, as Bedrock names it.
        temperature: How much the model is allowed to wander.
        settings: Where the key and the region are read from.

    Returns:
        The chat model. Building it opens no connection, so an unusable key
        is discovered on the first question rather than here.

    Raises:
        ModelConfigurationError: If the key or the region is missing.
    """
    from langchain_aws import ChatBedrockConverse

    token = _required(settings, "AWS_BEARER_TOKEN_BEDROCK")
    region = _required(settings, "AWS_REGION")
    # boto3 reads a Bedrock API key from the process environment and from
    # nowhere else, so a key that came out of `.env` has to be put there
    # before the client is built. An exported one already wins over the
    # file and is left exactly as it is.
    os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", token)
    return ChatBedrockConverse(
        model=model,
        region_name=region,
        temperature=temperature,
        max_tokens=BEDROCK_MAX_TOKENS,
        disable_streaming=True,
    )


def _required(settings: Mapping[str, str], name: str) -> str:
    """Return one setting the hosted backend cannot be built without.

    Args:
        settings: Where the setting is looked for.
        name: The setting to read.

    Returns:
        Its value.

    Raises:
        ModelConfigurationError: If it is absent or empty, said in terms of
            what the user has to do about it.
    """
    value = (settings.get(name) or "").strip()
    if not value:
        raise ModelConfigurationError(
            f"{name} is not set, and answering from {BEDROCK} needs it. Add it "
            f"to {ENV_FILE} or export it, or unset {BACKEND_VARIABLE} to "
            f"answer from the local model instead."
        )
    return value


def _environment() -> Mapping[str, str]:
    """Read the settings the factory chooses from.

    Returns:
        The process environment over ``.env``, the way the corpus scripts
        read theirs. A missing file is not an error: an exported variable
        is as good a way to say which backend to use.
    """
    from infra.config import load_env

    return load_env(ENV_FILE)
