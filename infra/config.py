"""Settings shared by the provisioning script and the CDK stack.

Configuration lives in an environment file (``.env.admin`` by default) that is
never committed, because the project ARN written into it contains the account
id. Values already exported in the process environment win over the file, so a
one-off run can override a setting without editing it.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_ENV_FILE = Path(".env.admin")

#: Cost-allocation tag key applied to the Bedrock project. The value comes from
#: ``AWS_PROJECT_TAG``.
PROJECT_TAG_KEY = "Project"


class ConfigError(Exception):
    """A required setting is missing or unusable."""


def load_env(env_file: Path | str = DEFAULT_ENV_FILE) -> dict[str, str]:
    """Read an environment file, letting the real environment override it.

    Args:
        env_file: Path to the environment file. A missing file is not an
            error; the process environment may supply everything on its own.

    Returns:
        The merged settings, with empty values dropped.
    """
    from_file = {k: v for k, v in dotenv_values(env_file).items() if v}
    merged = {**from_file, **os.environ}
    return {k: v for k, v in merged.items() if v}


def require(env: dict[str, str], key: str) -> str:
    """Return ``key`` from ``env``, or raise a readable error.

    Args:
        env: Settings as returned by :func:`load_env`.
        key: Name of the setting to read.

    Returns:
        The setting's value.

    Raises:
        ConfigError: If the setting is absent or empty.
    """
    value = env.get(key)
    if not value:
        raise ConfigError(
            f"{key} is not set. Add it to {DEFAULT_ENV_FILE} or export it "
            f"before running."
        )
    return value
