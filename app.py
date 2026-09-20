"""CDK app entry point.

Synthesize with ``uv run cdk synth`` and deploy with ``uv run cdk deploy``.
The deployed policy is what a Bedrock API key is then minted against — see
the README for the order.
"""

from __future__ import annotations

import os
import sys

import aws_cdk as cdk

from infra.config import ConfigError, load_env
from infra.stack import CorpusQueryStack, stack_environment


def main() -> None:
    """Build the app and synthesize it."""
    env_values = load_env()
    app = cdk.App()
    CorpusQueryStack(
        app,
        "CorpusQueryStack",
        env_values=env_values,
        env=stack_environment(env_values, os.environ.get("CDK_DEFAULT_ACCOUNT")),
    )
    app.synth()


if __name__ == "__main__":
    try:
        main()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
