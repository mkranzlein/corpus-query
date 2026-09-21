"""Shared builder for the Bedrock-backed Anthropic client.

``bedrock_smoke_test.py``, ``generate_transcripts.py``, and ``enrich.py`` each
make direct calls through the ``anthropic`` SDK's Bedrock client rather than
through LangChain, and each needs the same client built the same way. This
module is the one place that happens, so the three scripts stay in step
instead of drifting as each is edited on its own.

This is deliberately narrow: it builds the client the scripts already build,
nothing more. It is not a step toward a client shared with the rest of the
application — the agent's own chat model reaches Bedrock through LangChain,
a separate path that this module has no bearing on.
"""

from __future__ import annotations

from anthropic import AnthropicBedrock

from infra.config import require


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
