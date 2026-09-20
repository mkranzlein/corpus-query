"""One-off smoke test for the Bedrock Runtime API.

Nothing else in the repository has made a real inference call yet. Running
this script once proves that the endpoint, key, region, and model id all
line up, that structured output comes back parsed rather than as raw JSON
that needs hand parsing, and that a temperature is accepted.

The temperature is here only to be proven. This request would be no worse
without one, but the two scripts that spend real money both set one, and a
rejected sampling parameter is worth discovering on one short call rather
than part way through a batch of transcripts.

This is a developer tool, not part of the application: it lives here rather
than under :mod:`infra` because it will not grow into anything the
application depends on.

Run it with::

    uv run scripts/bedrock_smoke_test.py

Settings come from ``.env`` (not ``.env.admin``, which the provisioning
scripts use): ``AWS_BEARER_TOKEN_BEDROCK`` and ``AWS_REGION``.

Every run makes a real, billed inference call. Do not run this without
asking first — see CLAUDE.md.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from anthropic import AnthropicBedrock
from anthropic.types import Message
from pydantic import BaseModel

from infra.config import ConfigError, load_env, require

#: Environment file this script reads. Deliberately not ``infra.config``'s
#: default of ``.env.admin`` — that file holds AWS provisioning settings,
#: this one holds the inference client's.
ENV_FILE = ".env"

#: The US cross-region inference profile for Claude Sonnet 4.6, which is how
#: the model is offered rather than as a plain foundation-model id: a call is
#: routed to whichever US region has capacity for it.
MODEL = "us.anthropic.claude-sonnet-4-6"

#: Enough for the three short fields below and nothing more.
MAX_TOKENS = 1024

#: Sampling temperature, sent the same way the billed scripts send theirs:
#: through ``extra_body``, because the SDK dropped sampling controls from its
#: typed parameters when the models after this one stopped accepting them.
#: The value is arbitrary; that it is accepted at all is the point.
TEMPERATURE = 0.2

PROMPT = "In one sentence, name the capital of France and say whether it is coastal."


class SmokeTestAnswer(BaseModel):
    """Trivial structured output, used only to prove the parse path works."""

    capital: str
    is_coastal: bool
    summary: str


def build_client(env: dict[str, str]) -> AnthropicBedrock:
    """Build the Anthropic client pointed at Bedrock Runtime.

    Args:
        env: Settings as returned by :func:`infra.config.load_env`.

    Returns:
        A client configured with the key and region from ``env``.

    Raises:
        ConfigError: If a required setting is missing.
    """
    return AnthropicBedrock(
        api_key=require(env, "AWS_BEARER_TOKEN_BEDROCK"),
        aws_region=require(env, "AWS_REGION"),
    )


def describe_empty(message: Message) -> str:
    """Say why a response carried no parsed structured output.

    Args:
        message: The response that came back without parsed output.

    Returns:
        A sentence naming the likely cause, so the reader is not left to
        guess between a truncated response and a declined one.
    """
    if message.stop_reason == "max_tokens":
        return (
            f"the response was cut off at the {MAX_TOKENS}-token limit "
            f"before it was complete"
        )
    if message.stop_reason == "refusal":
        return "the model declined to answer"
    return (
        f"the response carried no parsed structured output "
        f"(stop reason: {message.stop_reason})"
    )


def run(client: AnthropicBedrock, region: str) -> int:
    """Make the call and print what it proves.

    Args:
        client: A configured client.
        region: The region the client was built with, for the printout.

    Returns:
        A process exit code.
    """
    message = client.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": PROMPT}],
        output_format=SmokeTestAnswer,
        extra_body={"temperature": TEMPERATURE},
    )
    parsed = message.parsed_output
    if parsed is None:
        print(f"error: {describe_empty(message)}", file=sys.stderr)
        return 1

    print(f"Requested model: {MODEL}")
    print(f"Temperature:     {TEMPERATURE}, accepted")
    print(f"Served by model: {message.model}")
    print(f"Region:          {region}")
    print(f"Response id:     {message.id}")
    print(f"capital:  {parsed.capital}")
    print(f"is_coastal: {parsed.is_coastal}")
    print(f"summary:  {parsed.summary}")
    return 0


def main(
    argv: list[str] | None = None,
    client_factory: Callable[[dict[str, str]], AnthropicBedrock] = build_client,
) -> int:
    """Run the script.

    Args:
        argv: Unused; accepted for symmetry with the other entry points.
        client_factory: Builds the client from settings. Overridable in
            tests so a fake client can stand in for the real one.

    Returns:
        A process exit code.
    """
    del argv
    try:
        env = load_env(ENV_FILE)
        region = require(env, "AWS_REGION")
        client = client_factory(env)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return run(client, region)


if __name__ == "__main__":
    raise SystemExit(main())
