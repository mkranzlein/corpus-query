"""Tests for the factory that picks the agent's chat model.

Nothing here calls a model, local or hosted. Building either client opens no
connection, so the factory's whole job — reading the settings, choosing a
backend, and handing back a client configured the way this project wants it —
can be asserted on directly, and a test run costs nothing either way.

The settings are passed in rather than read from the environment, so what a
developer happens to have in ``.env`` cannot change what these prove.
"""

from __future__ import annotations

import os

import pytest

from corpus_query.agent.model import (
    BACKEND_VARIABLE,
    BEDROCK,
    BEDROCK_MAX_TOKENS,
    BEDROCK_MODEL,
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    OLLAMA,
    ModelConfigurationError,
    load_chat_model,
    selected_backend,
)

#: Enough settings to build the hosted backend, with nothing real in them.
BEDROCK_SETTINGS = {
    BACKEND_VARIABLE: BEDROCK,
    "AWS_BEARER_TOKEN_BEDROCK": "not-a-real-key",
    "AWS_REGION": "us-east-1",
}


def test_told_nothing_it_answers_locally() -> None:
    """The default is the local model, so an unconfigured run bills nothing."""
    assert selected_backend(env={}) == OLLAMA
    assert type(load_chat_model(env={})).__name__ == "ChatOllama"


def test_a_bedrock_key_on_its_own_does_not_choose_bedrock() -> None:
    """Having credentials is not the same as asking to spend money.

    A key sits in ``.env`` because the corpus scripts need one. Letting its
    presence route questions to a billed model would mean the cost of
    answering depended on a file nobody edited for that purpose.
    """
    settings = {k: v for k, v in BEDROCK_SETTINGS.items() if k != BACKEND_VARIABLE}

    assert selected_backend(env=settings) == OLLAMA


def test_the_local_model_is_built_the_way_the_project_wants_it() -> None:
    """The local model is asked for by name, cold, with a sized window.

    It pins the context window in particular: 16384 was measured against the
    longest real turns rather than picked, and Ollama's own default silently
    evicts the system prompt when it is too small, so a change to that
    number should be a deliberate one.
    """
    model = load_chat_model(env={})

    assert model.model == DEFAULT_MODEL == "granite4.1:8b"
    assert model.temperature == DEFAULT_TEMPERATURE == 0.0
    assert model.num_ctx == DEFAULT_CONTEXT_WINDOW == 16384


def test_the_local_model_takes_overrides() -> None:
    """Every setting can be asked for, which is how a test or a tool pins one."""
    model = load_chat_model(
        OLLAMA, model="something-else:1b", temperature=0.7, context_window=2048
    )

    assert (model.model, model.temperature, model.num_ctx) == (
        "something-else:1b",
        0.7,
        2048,
    )


def test_bedrock_is_chosen_by_configuration(monkeypatch) -> None:
    """Setting the variable is what moves answering to the hosted model."""
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)

    assert selected_backend(env=BEDROCK_SETTINGS) == BEDROCK
    model = load_chat_model(env=BEDROCK_SETTINGS)

    assert type(model).__name__ == "ChatBedrockConverse"
    assert model.model_id == BEDROCK_MODEL == "us.anthropic.claude-sonnet-4-6"
    assert model.region_name == "us-east-1"
    assert model.temperature == DEFAULT_TEMPERATURE
    assert model.max_tokens == BEDROCK_MAX_TOKENS


def test_the_hosted_model_does_not_stream(monkeypatch) -> None:
    """Streaming is off, and that is a decision rather than a default.

    LangChain's Bedrock Converse model has had trouble streaming tool calls
    against cross-region inference profiles, which is the kind of model id
    this uses, and the agent awaits every reply whole regardless.
    """
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)

    assert load_chat_model(env=BEDROCK_SETTINGS).disable_streaming is True


def test_the_hosted_model_takes_a_different_model_id(monkeypatch) -> None:
    """A caller can name another Bedrock model without touching the module."""
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)

    model = load_chat_model(
        BEDROCK,
        model="us.anthropic.something-else",
        env={
            "AWS_BEARER_TOKEN_BEDROCK": "not-a-real-key",
            "AWS_REGION": "eu-west-1",
        },
    )

    assert model.model_id == "us.anthropic.something-else"
    assert model.region_name == "eu-west-1"


def test_the_backend_name_is_forgiving_about_spelling() -> None:
    """Case and stray whitespace do not decide which model answers."""
    assert selected_backend(env={BACKEND_VARIABLE: "  Bedrock \n"}) == BEDROCK
    assert selected_backend(env={BACKEND_VARIABLE: "OLLAMA"}) == OLLAMA


def test_an_empty_setting_is_treated_as_unset() -> None:
    """``CORPUS_QUERY_MODEL_BACKEND=`` is not a backend called the empty string."""
    assert selected_backend(env={BACKEND_VARIABLE: ""}) == OLLAMA


def test_a_backend_this_project_does_not_have_is_refused() -> None:
    """A typo answers from nothing rather than silently from the other one.

    The two backends differ in what they cost, so guessing which one was
    meant is the wrong thing to do.
    """
    with pytest.raises(ModelConfigurationError) as raised:
        load_chat_model(env={BACKEND_VARIABLE: "openai"})

    message = str(raised.value)
    assert "openai" in message
    assert BACKEND_VARIABLE in message


@pytest.mark.parametrize("missing", ["AWS_BEARER_TOKEN_BEDROCK", "AWS_REGION"])
def test_bedrock_without_its_settings_says_which_one(monkeypatch, missing) -> None:
    """The failure names the setting, the file, and the way out of it."""
    monkeypatch.delenv(missing, raising=False)
    settings = {k: v for k, v in BEDROCK_SETTINGS.items() if k != missing}

    with pytest.raises(ModelConfigurationError) as raised:
        load_chat_model(env=settings)

    message = str(raised.value)
    assert missing in message
    assert ".env" in message
    assert BACKEND_VARIABLE in message


def test_a_key_from_the_settings_file_reaches_boto(monkeypatch) -> None:
    """A key that came out of ``.env`` is exported before the client is built.

    boto3 reads a Bedrock API key from the process environment and from
    nowhere else, so a key the factory read from a file has to be put there
    or the first question fails unauthenticated.
    """
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)

    load_chat_model(env=BEDROCK_SETTINGS)

    assert os.environ["AWS_BEARER_TOKEN_BEDROCK"] == "not-a-real-key"


def test_an_exported_key_wins_over_the_file(monkeypatch) -> None:
    """A key already in the environment is left exactly as it is."""
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "exported-key")

    load_chat_model(env=BEDROCK_SETTINGS)

    assert os.environ["AWS_BEARER_TOKEN_BEDROCK"] == "exported-key"
