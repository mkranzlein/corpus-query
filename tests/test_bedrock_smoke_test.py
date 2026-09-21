"""Tests for the Bedrock Runtime smoke test.

These tests never talk to a real endpoint: the client is replaced with a
fake whose ``messages.parse`` returns a canned, parsed result.
"""

from __future__ import annotations

from pathlib import Path

from scripts.bedrock_smoke_test import (
    MODEL,
    PROMPT,
    TEMPERATURE,
    SmokeTestAnswer,
    main,
    run,
)

SETTINGS = {
    "AWS_BEARER_TOKEN_BEDROCK": "bedrock-api-key-fake",
    "AWS_REGION": "us-east-1",
}


class FakeMessage:
    """Stands in for the SDK's ``ParsedMessage``."""

    def __init__(self, parsed: SmokeTestAnswer | None, stop_reason: str = "end_turn"):
        self.parsed_output = parsed
        self.model = MODEL
        self.id = "msg_fake123"
        self.stop_reason = stop_reason


class FakeMessages:
    def __init__(self, parsed: SmokeTestAnswer | None, stop_reason: str = "end_turn"):
        self._parsed = parsed
        self._stop_reason = stop_reason
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return FakeMessage(self._parsed, self._stop_reason)


class FakeClient:
    def __init__(self, parsed: SmokeTestAnswer | None, stop_reason: str = "end_turn"):
        self.messages = FakeMessages(parsed, stop_reason)


ANSWER = SmokeTestAnswer(capital="Paris", is_coastal=False, summary="Not coastal.")


def test_run_prints_parsed_fields_and_provenance(capsys):
    client = FakeClient(ANSWER)

    exit_code = run(client, region="us-east-1")

    out = capsys.readouterr().out
    assert exit_code == 0
    assert f"Requested model: {MODEL}" in out
    assert f"Served by model: {MODEL}" in out
    assert "Region:          us-east-1" in out
    assert "Response id:     msg_fake123" in out
    assert "capital:  Paris" in out
    assert "is_coastal: False" in out
    assert "summary:  Not coastal." in out
    assert f"Temperature:     {TEMPERATURE}, accepted" in out


def test_run_uses_structured_output_request():
    client = FakeClient(ANSWER)

    run(client, region="us-east-1")

    [call] = client.messages.calls
    assert call["model"] == MODEL
    assert call["output_format"] is SmokeTestAnswer
    assert call["messages"] == [{"role": "user", "content": PROMPT}]
    assert call["max_tokens"] > 0
    assert call["extra_body"] == {"temperature": TEMPERATURE}


def test_run_reports_a_missing_parsed_result(capsys):
    client = FakeClient(None)

    exit_code = run(client, region="us-east-1")

    assert exit_code == 1
    assert "carried no parsed structured output" in capsys.readouterr().err


def test_run_says_when_the_response_was_cut_off(capsys):
    """A truncated response is a different problem from a declined one.

    Both arrive as no parsed output, and the fix for one is not the fix for
    the other, so the stop reason is read rather than the result alone.
    """
    client = FakeClient(None, stop_reason="max_tokens")

    exit_code = run(client, region="us-east-1")

    assert exit_code == 1
    assert "cut off" in capsys.readouterr().err


def test_main_reports_a_missing_setting(tmp_path: Path, monkeypatch, capsys):
    for key in SETTINGS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("AWS_BEARER_TOKEN_BEDROCK=fake\n", encoding="utf-8")
    monkeypatch.setattr("scripts.bedrock_smoke_test.ENV_FILE", str(env_file))

    exit_code = main()

    assert exit_code == 1
    assert "AWS_REGION is not set" in capsys.readouterr().err


def test_main_wires_settings_through_to_the_client(tmp_path: Path, monkeypatch):
    for key in SETTINGS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "".join(f"{k}={v}\n" for k, v in SETTINGS.items()), encoding="utf-8"
    )
    monkeypatch.setattr("scripts.bedrock_smoke_test.ENV_FILE", str(env_file))

    seen_env: dict[str, str] = {}

    def fake_client_factory(env: dict[str, str]):
        seen_env.update(env)
        return FakeClient(ANSWER)

    exit_code = main(client_factory=fake_client_factory)

    assert exit_code == 0
    assert seen_env["AWS_REGION"] == "us-east-1"
