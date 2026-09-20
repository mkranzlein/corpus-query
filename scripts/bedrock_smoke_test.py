"""One-off smoke test for the Bedrock Responses API.

Nothing else in the repository has made a real inference call yet. Running
this script once proves that the endpoint, key, project, and model id all
line up, and that structured output comes back parsed rather than as raw
JSON that needs hand parsing.

This is a developer tool, not part of the application: it lives here rather
than under :mod:`infra` because it will not grow into anything the
application depends on.

Run it with::

    uv run scripts/bedrock_smoke_test.py

Settings come from ``.env`` (not ``.env.admin``, which the provisioning
scripts use): ``OPENAI_API_KEY``, ``OPENAI_BASE_URL``, and ``OPENAI_PROJECT``.

Every run makes a real, billed inference call. Do not run this without
asking first — see CLAUDE.md.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from openai import OpenAI
from pydantic import BaseModel

from infra.config import ConfigError, load_env, require

#: Environment file this script reads. Deliberately not ``infra.config``'s
#: default of ``.env.admin`` — that file holds AWS provisioning settings,
#: this one holds the OpenAI-compatible client settings.
ENV_FILE = ".env"

#: A plain Bedrock model id, not a ``us.``-prefixed inference profile.
MODEL = "openai.gpt-5.6-sol"

PROMPT = "In one sentence, name the capital of France and say whether it is coastal."


class SmokeTestAnswer(BaseModel):
    """Trivial structured output, used only to prove the parse path works."""

    capital: str
    is_coastal: bool
    summary: str


def build_client(env: dict[str, str]) -> OpenAI:
    """Build the OpenAI client pointed at the Bedrock Mantle endpoint.

    Args:
        env: Settings as returned by :func:`infra.config.load_env`.

    Returns:
        A client configured with the key, endpoint, and project from ``env``.

    Raises:
        ConfigError: If a required setting is missing.
    """
    return OpenAI(
        api_key=require(env, "OPENAI_API_KEY"),
        base_url=require(env, "OPENAI_BASE_URL"),
        project=require(env, "OPENAI_PROJECT"),
    )


def run(client: OpenAI, project: str) -> int:
    """Make the call and print what it proves.

    Args:
        client: A configured OpenAI client.
        project: The project id the client was built with, for the printout.

    Returns:
        A process exit code.
    """
    response = client.responses.parse(
        model=MODEL,
        input=PROMPT,
        text_format=SmokeTestAnswer,
    )
    parsed = response.output_parsed
    if parsed is None:
        print(
            "error: the response did not include parsed structured output",
            file=sys.stderr,
        )
        return 1

    print(f"Requested model: {MODEL}")
    print(f"Served by model: {response.model}")
    print(f"Project:         {project}")
    print(f"Response id:     {response.id}")
    print(f"capital:  {parsed.capital}")
    print(f"is_coastal: {parsed.is_coastal}")
    print(f"summary:  {parsed.summary}")
    return 0


def main(
    argv: list[str] | None = None,
    client_factory: Callable[[dict[str, str]], OpenAI] = build_client,
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
        project = require(env, "OPENAI_PROJECT")
        client = client_factory(env)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return run(client, project)


if __name__ == "__main__":
    raise SystemExit(main())
