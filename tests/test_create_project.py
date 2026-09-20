"""Tests for the Bedrock project creation script."""

from __future__ import annotations

from pathlib import Path

import pytest

from infra.config import ConfigError
from infra.create_project import (
    PROJECT_ARN_KEY,
    ProvisioningError,
    build_request,
    extract_identifiers,
    format_api_error,
    main,
    render_dry_run,
    write_env_var,
)

SETTINGS = {
    "AWS_REGION": "us-east-1",
    "AWS_PROJECT_NAME": "corpus-query",
    "AWS_PROJECT_TAG": "corpus-query",
}


def test_build_request_uses_regional_endpoint():
    request = build_request(SETTINGS)
    assert request.url == (
        "https://bedrock-mantle.us-east-1.api.aws/v1/organization/projects"
    )


def test_build_request_tags_the_project():
    body = build_request(SETTINGS).body
    assert body["name"] == "corpus-query"
    assert body["tags"] == [{"key": "Project", "value": "corpus-query"}]


def test_build_request_reports_a_missing_setting():
    with pytest.raises(ConfigError, match="AWS_REGION"):
        build_request({k: v for k, v in SETTINGS.items() if k != "AWS_REGION"})


def test_render_dry_run_shows_method_url_and_body():
    rendered = render_dry_run(build_request(SETTINGS))
    assert rendered.startswith("POST https://bedrock-mantle.us-east-1.api.aws/")
    assert '"name": "corpus-query"' in rendered


def test_duplicate_name_reads_as_a_sentence():
    message = format_api_error(
        status=409,
        error_type="ConflictException",
        body='{"message": "Project already exists"}',
        project_name="corpus-query",
    )
    assert message == (
        "A project named 'corpus-query' already exists. Reuse it, or pick a "
        "different AWS_PROJECT_NAME."
    )


def test_duplicate_recognized_from_the_message_alone():
    message = format_api_error(
        status=400,
        error_type=None,
        body='{"message": "A project with that name already exists"}',
        project_name="corpus-query",
    )
    assert "already exists" in message
    assert "AWS_PROJECT_NAME" in message


def test_other_rejections_keep_the_api_detail():
    message = format_api_error(
        status=403,
        error_type="AccessDeniedException",
        body='{"message": "not authorized"}',
        project_name="corpus-query",
    )
    assert "HTTP 403" in message
    assert "AccessDeniedException: not authorized" in message


def test_unparseable_body_still_produces_a_message():
    message = format_api_error(
        status=500, error_type=None, body="<html>oops</html>", project_name="p"
    )
    assert "HTTP 500" in message
    assert "oops" in message


@pytest.mark.parametrize(
    "payload",
    [
        {
            "projectArn": "arn:aws:bedrock-mantle:::project/abc123",
            "projectId": "abc123",
        },
        {"arn": "arn:aws:bedrock-mantle:::project/abc123", "id": "abc123"},
    ],
)
def test_identifiers_read_from_either_field_spelling(payload):
    arn, project_id = extract_identifiers(payload)
    assert arn.endswith("project/abc123")
    assert project_id == "abc123"


def test_identifier_falls_back_to_the_arn_suffix():
    _, project_id = extract_identifiers(
        {"projectArn": "arn:aws:bedrock-mantle:::project/abc123"}
    )
    assert project_id == "abc123"


def test_unrecognized_response_warns_before_a_retry():
    with pytest.raises(ProvisioningError, match="Check the console"):
        extract_identifiers({"unexpected": "shape"})


def test_write_env_var_appends_to_an_existing_file(tmp_path: Path):
    env_file = tmp_path / ".env.admin"
    env_file.write_text("AWS_REGION=us-east-1\n", encoding="utf-8")

    write_env_var(env_file, PROJECT_ARN_KEY, "arn:aws:example")

    assert env_file.read_text(encoding="utf-8") == (
        "AWS_REGION=us-east-1\nAWS_PROJECT_ARN=arn:aws:example\n"
    )


def test_write_env_var_replaces_an_earlier_value(tmp_path: Path):
    env_file = tmp_path / ".env.admin"
    env_file.write_text(
        "AWS_PROJECT_ARN=arn:aws:old\nAWS_REGION=us-east-1\n", encoding="utf-8"
    )

    write_env_var(env_file, PROJECT_ARN_KEY, "arn:aws:new")

    assert env_file.read_text(encoding="utf-8") == (
        "AWS_PROJECT_ARN=arn:aws:new\nAWS_REGION=us-east-1\n"
    )


def test_write_env_var_creates_a_missing_file(tmp_path: Path):
    env_file = tmp_path / ".env.admin"

    write_env_var(env_file, PROJECT_ARN_KEY, "arn:aws:example")

    assert env_file.read_text(encoding="utf-8") == "AWS_PROJECT_ARN=arn:aws:example\n"


def test_dry_run_sends_nothing(tmp_path: Path, capsys, monkeypatch):
    for key in ("AWS_PROJECT_ARN", *SETTINGS):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env.admin"
    env_file.write_text(
        "".join(f"{k}={v}\n" for k, v in SETTINGS.items()), encoding="utf-8"
    )

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a dry run must not open a connection")

    monkeypatch.setattr("urllib.request.urlopen", refuse)

    assert main(["--dry-run", "--env-file", str(env_file)]) == 0

    out = capsys.readouterr().out
    assert "POST https://bedrock-mantle.us-east-1.api.aws/" in out
    assert "AWS_PROJECT_ARN" not in env_file.read_text(encoding="utf-8")


def test_missing_setting_exits_without_a_traceback(tmp_path: Path, capsys, monkeypatch):
    for key in SETTINGS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env.admin"
    env_file.write_text("AWS_REGION=us-east-1\n", encoding="utf-8")

    assert main(["--dry-run", "--env-file", str(env_file)]) == 1
    assert "AWS_PROJECT_NAME is not set" in capsys.readouterr().err
