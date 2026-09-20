"""Tests for the Bedrock Responses API smoke test.

These tests never talk to a real endpoint: the OpenAI client is replaced
with a fake whose ``responses.parse`` returns a canned, parsed result.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infra.config import ConfigError
from scripts.bedrock_smoke_test import (
    SmokeTestAnswer,
    build_client,
    main,
    run,
)

SETTINGS = {
    "OPENAI_API_KEY": "sk-fake",
    "OPENAI_BASE_URL": "https://example.invalid/v1",
    "OPENAI_PROJECT": "proj-fake",
}


class FakeParsedResponse:
    """Stands in for the SDK's ``ParsedResponse``."""

    def __init__(self, parsed: SmokeTestAnswer | None):
        self.output_parsed = parsed
        self.model = "openai.gpt-5.6-sol"
        self.id = "resp_fake123"


class FakeResponses:
    def __init__(self, parsed: SmokeTestAnswer | None):
        self._parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return FakeParsedResponse(self._parsed)


class FakeClient:
    def __init__(self, parsed: SmokeTestAnswer | None):
        self.responses = FakeResponses(parsed)


def test_run_prints_parsed_fields_and_provenance(capsys):
    answer = SmokeTestAnswer(capital="Paris", is_coastal=False, summary="Not coastal.")
    client = FakeClient(answer)

    exit_code = run(client, project="proj-fake")

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Requested model: openai.gpt-5.6-sol" in out
    assert "Served by model: openai.gpt-5.6-sol" in out
    assert "Project:         proj-fake" in out
    assert "Response id:     resp_fake123" in out
    assert "capital:  Paris" in out
    assert "is_coastal: False" in out
    assert "summary:  Not coastal." in out


def test_run_uses_structured_output_request(capsys):
    answer = SmokeTestAnswer(capital="Paris", is_coastal=False, summary="Not coastal.")
    client = FakeClient(answer)

    run(client, project="proj-fake")

    [call] = client.responses.calls
    assert call["model"] == "openai.gpt-5.6-sol"
    assert call["text_format"] is SmokeTestAnswer


def test_run_reports_a_missing_parsed_result(capsys):
    client = FakeClient(None)

    exit_code = run(client, project="proj-fake")

    assert exit_code == 1
    assert "did not include parsed" in capsys.readouterr().err


def test_main_reports_a_missing_setting(tmp_path: Path, monkeypatch, capsys):
    for key in SETTINGS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-fake\n", encoding="utf-8")
    monkeypatch.setattr("scripts.bedrock_smoke_test.ENV_FILE", str(env_file))

    exit_code = main()

    assert exit_code == 1
    assert "OPENAI_PROJECT is not set" in capsys.readouterr().err


def test_main_wires_settings_through_to_the_client(tmp_path: Path, monkeypatch):
    for key in SETTINGS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "".join(f"{k}={v}\n" for k, v in SETTINGS.items()), encoding="utf-8"
    )
    monkeypatch.setattr("scripts.bedrock_smoke_test.ENV_FILE", str(env_file))

    answer = SmokeTestAnswer(capital="Paris", is_coastal=False, summary="Not coastal.")
    seen_env: dict[str, str] = {}

    def fake_client_factory(env: dict[str, str]):
        seen_env.update(env)
        return FakeClient(answer)

    exit_code = main(client_factory=fake_client_factory)

    assert exit_code == 0
    assert seen_env["OPENAI_PROJECT"] == "proj-fake"


def test_build_client_reports_a_missing_key():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        build_client({k: v for k, v in SETTINGS.items() if k != "OPENAI_API_KEY"})


def test_build_client_uses_the_configured_endpoint_and_project():
    client = build_client(SETTINGS)

    assert str(client.base_url) == "https://example.invalid/v1/"
    assert client.project == "proj-fake"
