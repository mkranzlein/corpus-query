"""Tests for the transcript generator.

Nothing here talks to a real endpoint. The client is replaced by a fake that
records the request it was handed and returns a canned batch, so the tests
assert on what would have been sent and on what happens to what comes back.

The fake answers ``messages.stream``, which is how this script asks: a batch
of transcripts is long enough that the SDK will not wait for it in one piece.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from corpus_query.transcripts.length import transcript_words
from corpus_query.transcripts.summaries import NO_PRIOR_MEETINGS
from scripts.generate_transcripts import (
    COLD_TEMPERATURE,
    MAX_TOKENS,
    MODEL,
    WARM_TEMPERATURE,
    MeetingBatch,
    check_roster,
    describe_validation_error,
    existing_slugs,
    main,
    temperature_for,
    write_meeting,
)
from tests.conftest import REPO_ROOT

SETTINGS = {
    "AWS_BEARER_TOKEN_BEDROCK": "bedrock-api-key-fake",
    "AWS_REGION": "us-east-1",
}


class FakeMessage:
    """Stands in for the SDK's ``ParsedMessage``."""

    def __init__(self, parsed: MeetingBatch | None):
        self.parsed_output = parsed
        self.stop_reason = "end_turn"


class FakeStream:
    """The context manager a streamed request is used through."""

    def __init__(self, parsed: MeetingBatch | None, error: Exception | None):
        self._parsed = parsed
        self._error = error

    def __enter__(self) -> FakeStream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def get_final_message(self) -> FakeMessage:
        if self._error is not None:
            raise self._error
        return FakeMessage(self._parsed)


class FakeMessages:
    def __init__(self, parsed: MeetingBatch | None, error: Exception | None):
        self._parsed = parsed
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        return FakeStream(self._parsed, self._error)


class FakeClient:
    """A client that never leaves the process."""

    def __init__(
        self, parsed: MeetingBatch | None = None, error: Exception | None = None
    ):
        self.messages = FakeMessages(parsed, error)


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch) -> Path:
    """Write a settings file and point the script at it."""
    for key in SETTINGS:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "".join(f"{k}={v}\n" for k, v in SETTINGS.items()), encoding="utf-8"
    )
    monkeypatch.setattr("scripts.generate_transcripts.ENV_FILE", str(path))
    return path


@pytest.fixture
def run(tmp_path: Path, roster_path: Path, env_file: Path):
    """Return a callable that runs the script against a temporary corpus."""

    def runner(client: FakeClient | None = None, *args: str) -> int:
        return main(
            [
                "--out-dir",
                str(tmp_path / "transcripts"),
                "--roster",
                str(roster_path),
                "--db",
                str(tmp_path / "absent.db"),
                *args,
            ],
            client_factory=lambda env: client,
        )

    return runner


def conversation(words: int) -> list[dict[str, str]]:
    """Build turns holding ``words`` words between two people.

    Args:
        words: How many words are said in total.

    Returns:
        Turn dictionaries suitable for the meeting factory.

    """
    half = words // 2
    return [
        {"speaker": "Priya", "text": " ".join(["word"] * half)},
        {"speaker": "Marcus", "text": " ".join(["word"] * (words - half))},
    ]


@pytest.fixture
def batch_of(make_meeting):
    """Return a factory building a parsed batch from meeting overrides.

    Meetings come out long enough that their stated length is honest, since
    the generator rejects a batch whose headers disagree with its transcripts.
    """

    def factory(*overrides: dict[str, Any]) -> MeetingBatch:
        return MeetingBatch(
            meetings=[
                make_meeting(**({"turns": conversation(750)} | override))
                for override in overrides
            ]
        )

    return factory


def test_a_dry_run_prints_the_prompt_and_calls_nothing(run, capsys):
    client = FakeClient()

    exit_code = run(client, "--dry-run")

    assert exit_code == 0
    assert client.messages.calls == []
    out = capsys.readouterr().out
    assert "Write 5 meetings" in out
    assert NO_PRIOR_MEETINGS in out


def test_a_dry_run_reflects_the_flags_it_was_given(run, capsys):
    run(FakeClient(), "--dry-run", "--count", "3", "--words", "800")
    out = capsys.readouterr().out
    assert "Write 3 meetings" in out
    assert "800 transcript words" in out


def test_the_request_carries_the_prompt_schema_model_and_temperature(
    run, batch_of, capsys
):
    client = FakeClient(batch_of({}))

    assert run(client, "--count", "1") == 0

    [call] = client.messages.calls
    assert call["model"] == MODEL
    assert call["output_format"] is MeetingBatch
    assert call["extra_body"] == {"temperature": COLD_TEMPERATURE}
    assert call["max_tokens"] == MAX_TOKENS
    assert "Write 1 meeting." in call["messages"][0]["content"]


def test_one_run_makes_exactly_one_request(run, batch_of):
    client = FakeClient(batch_of({}, {"subject": "Pricing review"}))
    run(client, "--count", "2")
    assert len(client.messages.calls) == 1


def test_a_temperature_flag_overrides_the_default(run, batch_of):
    client = FakeClient(batch_of({}))
    run(client, "--count", "1", "--temperature", "0.3")
    assert client.messages.calls[0]["extra_body"] == {"temperature": 0.3}


def test_a_first_batch_is_colder_than_one_steered_by_summaries():
    assert temperature_for(prior_count=0, chosen=None) == COLD_TEMPERATURE
    assert temperature_for(prior_count=7, chosen=None) == WARM_TEMPERATURE
    assert temperature_for(prior_count=7, chosen=0.2) == 0.2


def test_a_meeting_is_written_as_json_and_markdown(run, batch_of, tmp_path):
    assert run(FakeClient(batch_of({})), "--count", "1") == 0

    out_dir = tmp_path / "transcripts"
    assert (out_dir / "rev-b-schedule.md").read_text().startswith("# Rev B schedule")
    written = json.loads((out_dir / "rev-b-schedule.json").read_text())
    assert written["subject"] == "Rev B schedule"
    assert written["date"] == "2026-03-04"


def test_a_run_appends_rather_than_replacing(run, batch_of, tmp_path):
    run(FakeClient(batch_of({})), "--count", "1")
    run(FakeClient(batch_of({"subject": "Pricing review"})), "--count", "1")

    written = sorted(path.name for path in (tmp_path / "transcripts").glob("*.json"))
    assert written == ["pricing-review.json", "rev-b-schedule.json"]


def test_a_repeated_subject_does_not_overwrite_the_first_one(run, batch_of, tmp_path):
    run(FakeClient(batch_of({})), "--count", "1")
    run(FakeClient(batch_of({"date": "2026-05-06"})), "--count", "1")

    out_dir = tmp_path / "transcripts"
    first = json.loads((out_dir / "rev-b-schedule.json").read_text())
    second = json.loads((out_dir / "rev-b-schedule-2.json").read_text())
    assert first["date"] == "2026-03-04"
    assert second["date"] == "2026-05-06"


def test_a_collision_within_one_batch_is_suffixed(run, batch_of, tmp_path):
    run(FakeClient(batch_of({}, {"date": "2026-05-06"})), "--count", "2")
    written = sorted(path.stem for path in (tmp_path / "transcripts").glob("*.json"))
    assert written == ["rev-b-schedule", "rev-b-schedule-2"]


def test_the_run_says_where_the_corpus_stands(run, batch_of, capsys):
    run(FakeClient(batch_of({})), "--count", "1")
    out = capsys.readouterr().out
    assert "0 of 20 meetings exist; this run asks for 1." in out
    assert "1 of 20 meetings now exist." in out


def test_a_batch_that_would_exceed_the_target_is_refused(run, batch_of, capsys):
    client = FakeClient(batch_of({}))

    exit_code = run(client, "--count", "5", "--target", "3")

    assert exit_code == 1
    assert client.messages.calls == []
    assert "3 left" in capsys.readouterr().err


def test_force_generates_past_the_target(run, batch_of):
    client = FakeClient(batch_of({}))
    assert run(client, "--count", "1", "--target", "0", "--force") == 0
    assert len(client.messages.calls) == 1


def test_the_report_compares_what_came_back_with_what_was_asked_for(
    run, batch_of, capsys
):
    run(FakeClient(batch_of({})), "--count", "1", "--words", "1200")
    out = capsys.readouterr().out
    assert "rev-b-schedule:" in out
    assert "Asked for about 1,200 words a meeting" in out


def test_a_name_off_the_roster_fails_the_run_and_writes_nothing(
    run, make_meeting, tmp_path, capsys
):
    stranger = make_meeting(
        attendees=["Priya", "Dana"],
        turns=[{"speaker": "Dana", "text": "I do not exist."}],
        action_items=[],
    )
    exit_code = run(FakeClient(MeetingBatch(meetings=[stranger])), "--count", "1")

    assert exit_code == 1
    assert not (tmp_path / "transcripts").exists()
    assert "Dana is not on the roster" in capsys.readouterr().err


def test_a_response_with_no_parsed_output_fails_the_run(run, capsys):
    assert run(FakeClient(None), "--count", "1") == 1
    assert "did not include parsed" in capsys.readouterr().err


def test_a_validation_failure_names_the_meeting_and_the_field(
    run, capsys, make_meeting
):
    try:
        MeetingBatch.model_validate(
            {
                "meetings": [
                    make_meeting().model_dump(),
                    make_meeting().model_dump() | {"date": "the fourth of March"},
                ]
            }
        )
    except ValidationError as error:
        failure = error
    else:  # pragma: no cover - the payload above is invalid by construction
        pytest.fail("the invalid payload validated")

    exit_code = run(FakeClient(error=failure), "--count", "2")

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "nothing was written" in err
    assert "meeting 2, date" in err


def test_a_batch_wide_failure_is_reported_without_a_meeting_number(make_meeting):
    try:
        MeetingBatch.model_validate({"meetings": "not a list"})
    except ValidationError as error:
        assert describe_validation_error(error)[0].startswith("the batch")
    else:  # pragma: no cover - the payload above is invalid by construction
        pytest.fail("the invalid payload validated")


def test_a_nested_field_is_named_by_its_path(make_meeting):
    try:
        MeetingBatch.model_validate(
            {"meetings": [make_meeting().model_dump() | {"turns": [{"speaker": "P"}]}]}
        )
    except ValidationError as error:
        assert "meeting 1, turns[0].text" in describe_validation_error(error)[0]
    else:  # pragma: no cover - the payload above is invalid by construction
        pytest.fail("the invalid payload validated")


def test_checking_the_roster_accepts_the_real_cast(make_meeting, roster_path):
    from corpus_query.transcripts.roster import first_names, read_roster

    roster = first_names(read_roster(roster_path))
    assert check_roster([make_meeting()], roster) == []


def test_a_short_batch_is_reported_rather_than_rejected(
    run, batch_of, tmp_path, capsys
):
    """A batch that undershoots the word target is a judgment call, not an error."""
    exit_code = run(FakeClient(batch_of({})), "--count", "1", "--words", "1500")

    assert exit_code == 0
    assert (tmp_path / "transcripts" / "rev-b-schedule.json").is_file()
    out = capsys.readouterr().out
    assert "Asked for about 1,500 words a meeting; averaged 750." in out


def test_the_report_counts_only_spoken_words(make_meeting):
    meeting = make_meeting(turns=conversation(750))
    assert transcript_words(meeting) == 750


def test_existing_slugs_are_read_from_the_json_files(tmp_path: Path):
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()
    (out_dir / "rev-b-schedule.json").write_text("{}")
    (out_dir / "rev-b-schedule.md").write_text("# Rev B schedule")
    assert existing_slugs(out_dir) == {"rev-b-schedule"}


def test_a_missing_output_directory_counts_as_an_empty_corpus(tmp_path: Path):
    assert existing_slugs(tmp_path / "not-there") == set()


def test_writing_never_overwrites_an_existing_file(make_meeting, tmp_path: Path):
    out_dir = tmp_path / "transcripts"
    first = write_meeting(make_meeting(), out_dir, taken=set())
    second = write_meeting(make_meeting(), out_dir, taken={first})
    assert (first, second) == ("rev-b-schedule", "rev-b-schedule-2")


def test_a_missing_setting_stops_the_run_before_any_call(
    tmp_path: Path, roster_path: Path, monkeypatch, capsys
):
    for key in SETTINGS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("AWS_BEARER_TOKEN_BEDROCK=fake\n", encoding="utf-8")
    monkeypatch.setattr("scripts.generate_transcripts.ENV_FILE", str(env_file))

    from scripts.generate_transcripts import build_client

    exit_code = main(
        [
            "--out-dir",
            str(tmp_path / "transcripts"),
            "--roster",
            str(roster_path),
            "--db",
            str(tmp_path / "absent.db"),
        ],
        client_factory=build_client,
    )

    assert exit_code == 1
    assert "AWS_REGION is not set" in capsys.readouterr().err


def test_a_missing_roster_stops_the_run(tmp_path: Path, env_file: Path, capsys):
    exit_code = main(
        ["--roster", str(tmp_path / "absent.md"), "--out-dir", str(tmp_path / "out")],
        client_factory=lambda env: FakeClient(),
    )
    assert exit_code == 1
    assert "roster" in capsys.readouterr().err


def test_the_committed_roster_is_where_the_script_expects_it():
    assert (REPO_ROOT / "data" / "roster.md").is_file()
