"""Generate a batch of meeting transcripts.

The corpus is built a batch at a time rather than in one call. A run asks for a
handful of meetings, appends them to what is already on disk, and reports how
much of the target is left. Once a batch has been ingested, the next run is
told what the earlier meetings were about, so the corpus does not collapse into
twenty variations of the same status meeting.

Run it with::

    uv run scripts/generate_transcripts.py --dry-run   # print the prompt
    uv run scripts/generate_transcripts.py             # generate a batch

Settings come from ``.env``: ``AWS_BEARER_TOKEN_BEDROCK`` and
``AWS_REGION``.

Every run without ``--dry-run`` makes a real, billed inference call. Do not run
this without asking first — see CLAUDE.md.

Nothing is written unless the whole batch validates. A partly written batch
would be worse than none: it would have to be reconciled by hand against a
corpus whose whole point is that its contents are known.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from anthropic import AnthropicBedrock
from pydantic import BaseModel, Field, ValidationError

from corpus_query.transcripts.length import transcript_words
from corpus_query.transcripts.prompt import PromptError, build_prompt
from corpus_query.transcripts.render import render_meeting
from corpus_query.transcripts.roster import (
    DEFAULT_ROSTER_FILE,
    RosterError,
    first_names,
    read_roster,
)
from corpus_query.transcripts.schema import Meeting, Meetings
from corpus_query.transcripts.slugs import unique_slug
from corpus_query.transcripts.summaries import DEFAULT_DATABASE_FILE, read_summaries
from infra.config import ConfigError, load_env, require

#: Environment file this script reads, holding the inference client's
#: settings rather than the AWS provisioning ones.
ENV_FILE = ".env"

#: The US cross-region inference profile for Claude Sonnet 4.6, which is how
#: the model is offered rather than as a plain foundation-model id: a call is
#: routed to whichever US region has capacity for it.
MODEL = "us.anthropic.claude-sonnet-4-6"

#: Ceiling on one batch. A batch is the largest thing this project asks for —
#: several meetings of transcript in a single response — so the ceiling is
#: generous and the request is streamed. Left well above what a batch needs,
#: because a response cut off part way through is thrown away whole.
MAX_TOKENS = 32_000

#: Meetings one run asks for. Small enough that a bad batch is cheap to throw
#: away, and that the response fits comfortably in one call.
DEFAULT_COUNT = 5

#: Transcript words per meeting, spoken text only.
DEFAULT_WORDS = 1500

#: How many meetings the finished corpus holds. Reached over several runs.
CORPUS_TARGET = 20

#: Where generated transcripts are written.
DEFAULT_OUTPUT_DIR = Path("data/transcripts")

#: Temperature for a batch generated with no prior summaries to steer it. The
#: only thing keeping that batch varied is the prompt, so it is not pushed
#: hard.
COLD_TEMPERATURE = 0.7

#: Temperature once summaries are being sent. Later batches are already
#: constrained away from repeating earlier ones, so they can afford more drift.
WARM_TEMPERATURE = 0.9


class MeetingBatch(BaseModel):
    """What one request returns.

    Structured output needs an object at the top level, so the list of
    meetings is wrapped rather than returned bare. The list itself is the
    schema the meetings are validated against.
    """

    meetings: Meetings = Field(description="The generated meetings, in any order.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Arguments to parse. Defaults to the process arguments.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Generate a batch of meeting transcripts.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"how many meetings to ask for (default: {DEFAULT_COUNT})",
    )
    parser.add_argument(
        "--words",
        type=int,
        default=DEFAULT_WORDS,
        help=(
            f"transcript words per meeting, spoken text only (default: {DEFAULT_WORDS})"
        ),
    )
    parser.add_argument(
        "--target",
        type=int,
        default=CORPUS_TARGET,
        help=f"how many meetings the finished corpus holds (default: {CORPUS_TARGET})",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=(
            f"sampling temperature (default: {COLD_TEMPERATURE} for a first "
            f"batch, {WARM_TEMPERATURE} once prior summaries are being sent)"
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"where to write transcripts (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--roster",
        type=Path,
        default=DEFAULT_ROSTER_FILE,
        help=f"the staff roster (default: {DEFAULT_ROSTER_FILE})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE_FILE,
        help=(
            f"document store holding prior summaries; a missing one is the "
            f"normal first-batch case (default: {DEFAULT_DATABASE_FILE})"
        ),
    )
    parser.add_argument("--model", default=MODEL, help=f"model id (default: {MODEL})")
    parser.add_argument(
        "--force",
        action="store_true",
        help="generate even though the batch would take the corpus past the target",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the assembled prompt and exit without calling anything",
    )
    return parser.parse_args(argv)


def existing_slugs(out_dir: Path) -> set[str]:
    """Return the slugs already written.

    Args:
        out_dir: Where transcripts are written.

    Returns:
        One slug per meeting on disk, taken from the JSON filenames. Empty
        when the directory does not exist yet.
    """
    if not out_dir.is_dir():
        return set()
    return {path.stem for path in out_dir.glob("*.json")}


def temperature_for(prior_count: int, chosen: float | None) -> float:
    """Return the temperature to sample at.

    Args:
        prior_count: How many prior summaries the prompt carries.
        chosen: A temperature given on the command line, if any.

    Returns:
        The chosen temperature, or the default for this kind of batch.
    """
    if chosen is not None:
        return chosen
    return WARM_TEMPERATURE if prior_count else COLD_TEMPERATURE


def describe_validation_error(error: ValidationError) -> list[str]:
    """Turn a batch validation failure into one line per problem.

    The location pydantic reports starts at the wrapper field, so it is
    rewritten to name the meeting by position and the field within it. That
    is what someone reading the failure needs: which meeting, which field.

    Args:
        error: The failure raised while validating the batch.

    Returns:
        One readable line per problem.
    """
    lines = []
    for problem in error.errors():
        location = list(problem["loc"])
        if location[:1] == ["meetings"]:
            location = location[1:]
        where = "the batch"
        if location and isinstance(location[0], int):
            where = f"meeting {location[0] + 1}"
            location = location[1:]
        field = _format_path(location)
        lines.append(f"{where}{f', {field}' if field else ''}: {problem['msg']}")
    return lines


def _format_path(location: list[object]) -> str:
    """Render a field path as ``turns[3].text``.

    Args:
        location: The remaining location parts, after the meeting.

    Returns:
        The path, or an empty string when the problem is the meeting itself.
    """
    path = ""
    for part in location:
        path += f"[{part}]" if isinstance(part, int) else f".{part}" if path else part
    return path


def check_roster(meetings: Meetings, roster: tuple[str, ...]) -> list[str]:
    """Check that every name in a batch is someone who exists.

    The schema already guarantees a meeting is internally consistent — a
    speaker and an action item owner both appear in that meeting's attendee
    list — but it does not read the roster, since that is file I/O and the
    schema stays pure. This is the check that the cast is the real one.

    Args:
        meetings: The generated batch.
        roster: Every first name on the roster.

    Returns:
        One line per name that is not on the roster.
    """
    known = set(roster)
    problems = []
    for index, meeting in enumerate(meetings, start=1):
        named = {
            "attendee": set(meeting.attendees),
            "speaker": {turn.speaker for turn in meeting.turns},
            "action item owner": {item.assignee for item in meeting.action_items},
        }
        for role, names in named.items():
            for stranger in sorted(names - known):
                problems.append(
                    f"meeting {index} ({meeting.subject!r}): {role} {stranger} "
                    f"is not on the roster"
                )
    return problems


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


def request_batch(
    client: AnthropicBedrock, model: str, prompt: str, temperature: float
) -> MeetingBatch | None:
    """Ask for one batch of meetings.

    The request is streamed because the response is long: the SDK refuses a
    non-streamed request whose ceiling implies more than ten minutes of
    generation, and a batch of transcripts is exactly that. Nothing is shown
    as it arrives — the batch is only useful once it has all validated — so
    the stream is drained and the finished message taken from it.

    ``temperature`` goes through ``extra_body`` because the SDK dropped it
    from its typed parameters: the models released after this one reject
    sampling controls outright. Sonnet 4.6 still honours it, and variety
    across batches is the whole reason this script has a temperature at all.

    Args:
        client: A configured client.
        model: The model id to call.
        prompt: The assembled prompt.
        temperature: What to sample at.

    Returns:
        The parsed batch, or ``None`` if the response carried no parsed
        structured output.
    """
    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
        output_format=MeetingBatch,
        extra_body={"temperature": temperature},
    ) as stream:
        return stream.get_final_message().parsed_output


def write_meeting(meeting: Meeting, out_dir: Path, taken: set[str]) -> str:
    """Write one meeting as JSON and as markdown.

    Args:
        meeting: A validated meeting.
        out_dir: Where transcripts are written.
        taken: Slugs already spoken for. The new slug is added to it.

    Returns:
        The slug the meeting was written under.
    """
    slug = unique_slug(meeting.subject, taken)
    taken.add(slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / f"{slug}.json").open("x", encoding="utf-8") as handle:
        json.dump(meeting.model_dump(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    with (out_dir / f"{slug}.md").open("x", encoding="utf-8") as handle:
        handle.write(render_meeting(meeting))
    return slug


def report(meetings: Meetings, slugs: list[str], words: int) -> None:
    """Print what the batch produced against what it was asked for.

    Args:
        meetings: The generated batch.
        slugs: The slug each meeting was written under, in the same order.
        words: The per-meeting word target the run asked for.
    """
    counts = [transcript_words(meeting) for meeting in meetings]
    for meeting, slug, count in zip(meetings, slugs, counts, strict=True):
        print(
            f"  {slug}: {count:,} words, {len(meeting.attendees)} attendees, "
            f"{len(meeting.turns)} turns"
        )
    average = sum(counts) // len(counts)
    print(f"Asked for about {words:,} words a meeting; averaged {average:,}.")


def announce_progress(existing: int, count: int, target: int) -> None:
    """Say where the corpus stands before a run adds to it.

    Args:
        existing: How many meetings are already on disk.
        count: How many this run asks for.
        target: How many the finished corpus holds.
    """
    print(f"{existing} of {target} meetings exist; this run asks for {count}.")


def main(
    argv: list[str] | None = None,
    client_factory: Callable[[dict[str, str]], AnthropicBedrock] = build_client,
) -> int:
    """Run the script.

    Args:
        argv: Command-line arguments. Defaults to the process arguments.
        client_factory: Builds the client from settings. Overridable in tests
            so a fake client can stand in for the real one.

    Returns:
        A process exit code.
    """
    args = parse_args(argv)
    if args.count < 1:
        print("error: --count has to be at least 1", file=sys.stderr)
        return 1

    try:
        people = read_roster(args.roster)
        prior = read_summaries(args.db)
        prompt = build_prompt(args.count, args.words, people, prior)
    except (RosterError, PromptError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    taken = existing_slugs(args.out_dir)
    announce_progress(len(taken), args.count, args.target)
    if len(taken) + args.count > args.target and not args.force:
        remaining = max(0, args.target - len(taken))
        print(
            f"error: that would take the corpus past {args.target}. "
            f"{remaining} left; ask for at most that, or pass --force.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(prompt)
        return 0

    temperature = temperature_for(len(prior), args.temperature)
    try:
        env = load_env(ENV_FILE)
        client = client_factory(env)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Calling {args.model} at temperature {temperature}.")
    try:
        batch = request_batch(client, args.model, prompt, temperature)
    except ValidationError as exc:
        print(
            "error: the response did not validate; nothing was written.",
            file=sys.stderr,
        )
        for line in describe_validation_error(exc):
            print(f"  {line}", file=sys.stderr)
        return 1

    if batch is None:
        print(
            "error: the response did not include parsed structured output",
            file=sys.stderr,
        )
        return 1

    problems = check_roster(batch.meetings, first_names(people))
    if problems:
        print("error: the batch was rejected; nothing was written.", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1

    if len(batch.meetings) != args.count:
        print(
            f"note: asked for {args.count} meetings and got {len(batch.meetings)}.",
            file=sys.stderr,
        )

    slugs = [write_meeting(meeting, args.out_dir, taken) for meeting in batch.meetings]
    report(batch.meetings, slugs, args.words)
    print(f"{len(taken)} of {args.target} meetings now exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
