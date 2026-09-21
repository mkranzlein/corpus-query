"""Tests for the shared Bedrock client builder.

These tests never talk to a real endpoint: constructing ``AnthropicBedrock``
makes no network call, so checking the attributes it was built with is
enough.
"""

from __future__ import annotations

import pytest

from infra.config import ConfigError
from scripts.bedrock_client import build_client

SETTINGS = {
    "AWS_BEARER_TOKEN_BEDROCK": "bedrock-api-key-fake",
    "AWS_REGION": "us-east-1",
}


def test_build_client_uses_the_configured_key_and_region():
    client = build_client(SETTINGS)

    assert client.api_key == "bedrock-api-key-fake"
    assert client.aws_region == "us-east-1"


def test_build_client_reports_a_missing_key():
    with pytest.raises(ConfigError, match="AWS_BEARER_TOKEN_BEDROCK"):
        build_client(
            {k: v for k, v in SETTINGS.items() if k != "AWS_BEARER_TOKEN_BEDROCK"}
        )


def test_build_client_reports_a_missing_region():
    with pytest.raises(ConfigError, match="AWS_REGION"):
        build_client({k: v for k, v in SETTINGS.items() if k != "AWS_REGION"})
