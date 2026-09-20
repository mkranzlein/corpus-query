"""Create the Bedrock project that inference is attributed to.

Bedrock's Projects API is REST-only: there is no CLI command and no SDK
client for it, so creation is a SigV4-signed HTTPS request rather than a CDK
resource. The project carries a cost-allocation tag, and its ARN is what the
IAM policy in :mod:`infra.stack` scopes inference permission to.

Run it with::

    uv run python -m infra.create_project [--dry-run]

Long-term Bedrock API keys can only get and list projects, so this needs
admin credentials from the usual boto3 credential chain.

The request body follows the documented example for the API. Two other
details are inferred from the shape of the ARN in the AWS documentation
rather than confirmed against a live call: the SigV4 signing service name
(:data:`SIGNING_SERVICE`) and the spelling of the response fields. The
response reader accepts the plausible spellings and says what it saw when
none of them match, so a wrong guess surfaces as a readable error.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infra.config import (
    DEFAULT_ENV_FILE,
    PROJECT_TAG_KEY,
    ConfigError,
    load_env,
    require,
)

#: Service name used when signing. Inferred from the ``bedrock-mantle`` ARN
#: namespace in the AWS documentation; unverified against a live call.
SIGNING_SERVICE = "bedrock-mantle"

#: Where the created project's ARN is recorded for the CDK stack to read.
PROJECT_ARN_KEY = "AWS_PROJECT_ARN"

_HOST_TEMPLATE = "bedrock-mantle.{region}.api.aws"
_PROJECTS_PATH = "/v1/organization/projects"
_TIMEOUT_SECONDS = 30

_ARN_FIELDS = ("projectArn", "arn", "ProjectArn")
_ID_FIELDS = ("projectId", "id", "ProjectId")


class ProvisioningError(Exception):
    """Something went wrong that the operator needs to read, not debug."""


@dataclass(frozen=True)
class ProjectRequest:
    """The request that creates one Bedrock project."""

    region: str
    name: str
    tag_value: str

    @property
    def url(self) -> str:
        """Full URL of the projects endpoint in this region."""
        return f"https://{_HOST_TEMPLATE.format(region=self.region)}{_PROJECTS_PATH}"

    @property
    def body(self) -> dict[str, Any]:
        """JSON body describing the project to create."""
        return {
            "name": self.name,
            "tags": {PROJECT_TAG_KEY: self.tag_value},
        }

    def encoded_body(self) -> bytes:
        """Return the body as the bytes that get signed and sent."""
        return json.dumps(self.body).encode("utf-8")


def build_request(env: dict[str, str]) -> ProjectRequest:
    """Assemble the creation request from the configured settings.

    Args:
        env: Settings as returned by :func:`infra.config.load_env`.

    Returns:
        The request to sign and send.

    Raises:
        ConfigError: If a required setting is missing.
    """
    return ProjectRequest(
        region=require(env, "AWS_REGION"),
        name=require(env, "AWS_PROJECT_NAME"),
        tag_value=require(env, "AWS_PROJECT_TAG"),
    )


def render_dry_run(request: ProjectRequest) -> str:
    """Describe the request in the form it would be sent.

    The rendering is deliberately unsigned: a dry run should not need
    credentials, and the ``Authorization`` header carries no information
    worth previewing.

    Args:
        request: The request that would be sent.

    Returns:
        A human-readable rendering of the request.
    """
    body = json.dumps(request.body, indent=2)
    return (
        f"POST {request.url}\n"
        f"Content-Type: application/json\n"
        f"Authorization: AWS4-HMAC-SHA256 <signed at send time, "
        f"service={SIGNING_SERVICE}>\n"
        f"\n"
        f"{body}"
    )


def sign(request: ProjectRequest, body: bytes) -> dict[str, str]:
    """Sign the request with SigV4 and return the headers to send.

    The caller passes the encoded body rather than letting this function
    encode its own copy, because SigV4 signs a hash of the body: signing one
    encoding and sending another would fail as a signature mismatch, which is
    an unpleasant thing to diagnose.

    Args:
        request: The request to sign.
        body: The exact bytes that will be sent as the request body.

    Returns:
        The signed headers, including ``Authorization``.

    Raises:
        ProvisioningError: If no AWS credentials are available.
    """
    import boto3
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise ProvisioningError(
            "No AWS credentials found. Configure admin credentials before "
            "creating the project; a Bedrock API key cannot do it."
        )

    signable = AWSRequest(
        method="POST",
        url=request.url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(
        credentials.get_frozen_credentials(), SIGNING_SERVICE, request.region
    ).add_auth(signable)
    return dict(signable.headers)


def send(request: ProjectRequest) -> dict[str, Any]:
    """Send the signed request and return the decoded response.

    Args:
        request: The request to send.

    Returns:
        The parsed JSON response body.

    Raises:
        ProvisioningError: If the API rejects the request or is unreachable.
    """
    body = request.encoded_body()
    http_request = urllib.request.Request(
        request.url,
        data=body,
        headers=sign(request, body),
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=_TIMEOUT_SECONDS) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise ProvisioningError(
            format_api_error(
                status=exc.code,
                error_type=exc.headers.get("x-amzn-errortype"),
                body=exc.read().decode("utf-8", errors="replace"),
                project_name=request.name,
            )
        ) from exc
    except urllib.error.URLError as exc:
        raise ProvisioningError(
            f"Could not reach {request.url}: {exc.reason}. Check the region "
            f"and that the Projects API is available there."
        ) from exc


def format_api_error(
    status: int, error_type: str | None, body: str, project_name: str
) -> str:
    """Turn an API rejection into a sentence an operator can act on.

    Args:
        status: HTTP status code of the rejection.
        error_type: Value of the ``x-amzn-errortype`` header, if any.
        body: Raw response body.
        project_name: Name the request tried to use, for the duplicate case.

    Returns:
        A one- or two-sentence explanation.
    """
    message = ""
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {}
    if isinstance(parsed, dict):
        message = str(parsed.get("message") or parsed.get("Message") or "")
        error_type = error_type or str(parsed.get("__type") or "") or None

    short_type = (error_type or "").split("#")[-1].split(":")[0]
    duplicate = (
        short_type
        in {
            "ConflictException",
            "ResourceAlreadyExistsException",
        }
        or "already exists" in message.lower()
    )
    if duplicate or status == 409:
        return (
            f"A project named {project_name!r} already exists. Reuse it, or "
            f"pick a different AWS_PROJECT_NAME."
        )

    detail = message or body.strip() or "no details returned"
    prefix = f"{short_type}: " if short_type else ""
    return f"The Projects API rejected the request (HTTP {status}). {prefix}{detail}"


def extract_identifiers(payload: dict[str, Any]) -> tuple[str, str]:
    """Pull the ARN and id out of a creation response.

    Args:
        payload: The parsed response body.

    Returns:
        The project's ARN and its id.

    Raises:
        ProvisioningError: If neither is present under a known field name.
    """
    arn = _first_present(payload, _ARN_FIELDS)
    project_id = _first_present(payload, _ID_FIELDS)
    if arn and project_id:
        return arn, project_id
    if arn and not project_id:
        return arn, arn.rsplit("/", 1)[-1]
    raise ProvisioningError(
        "The project may have been created, but the response did not contain "
        "an ARN under any expected field name. Fields returned: "
        f"{', '.join(sorted(payload)) or '(none)'}. Check the console before "
        "retrying, so a second project is not created."
    )


def _first_present(payload: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    """Return the first non-empty string among ``fields``, if any."""
    for field in fields:
        value = payload.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def write_env_var(env_file: Path, key: str, value: str) -> None:
    """Record a setting in the environment file, replacing any earlier value.

    Args:
        env_file: File to write to. It is created if it does not exist.
        key: Setting name.
        value: Setting value.
    """
    lines = (
        env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    )
    replacement = f"{key}={value}"
    for index, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the script.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        A process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the request that would be sent, and send nothing",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"environment file to read settings from (default: {DEFAULT_ENV_FILE})",
    )
    args = parser.parse_args(argv)

    try:
        request = build_request(load_env(args.env_file))
        if args.dry_run:
            print(render_dry_run(request))
            return 0
        arn, project_id = extract_identifiers(send(request))
    except (ConfigError, ProvisioningError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    write_env_var(args.env_file, PROJECT_ARN_KEY, arn)
    print(f"Created project {request.name!r}")
    print(f"  ARN: {arn}")
    print(f"  ID:  {project_id}")
    print(f"Wrote {PROJECT_ARN_KEY} to {args.env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
