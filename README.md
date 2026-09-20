# corpus-query

Query a corpus of documents with a language model, reaching Amazon Bedrock
through its OpenAI-compatible endpoint. You point the application at that
endpoint with an inference API key; nothing else needs to be set up first.

## Usage

The application itself is not built yet, so there is no run command to give
here. This section will document it once it exists.

## Development

```bash
uv sync
uv run pytest          # tests
pre-commit run --all-files
```

Hooks run ruff, gitleaks, and a Conventional Commits check. Install them once
with `pre-commit install` and `pre-commit install --hook-type commit-msg`.

## Provisioning (reference only)

This repository also holds the AWS provisioning behind the Bedrock endpoint:
a Bedrock project that inference is billed to, an IAM policy that permits
inference against that project and nothing else, and a budget alarm. It
documents how the account was set up — it is not something a user of the
application needs to run, or even look at, to get an inference key working.
If you only have a key, you can stop reading here.

What follows is a record of the steps that produced the current setup, kept
for anyone who needs to reproduce, audit, or extend the provisioning itself.

### Requirements

- Python 3.14 and [uv](https://docs.astral.sh/uv/)
- The [AWS CDK CLI](https://docs.aws.amazon.com/cdk/v2/guide/cli.html)
  (`npm install -g aws-cdk`), which runs the app through `uv` for you
- AWS credentials for an identity that can create Bedrock projects, IAM
  policies, and budgets
- The target account and region [bootstrapped for
  CDK](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html)
  (`cdk bootstrap`), if they have not been already

### Configuration

Settings live in `.env.admin`, which is gitignored and never committed: the
project ARN it ends up holding contains the account id. Anything exported in
the shell overrides the file.

| Setting | Meaning |
| --- | --- |
| `AWS_REGION` | Region the project and stack live in |
| `AWS_PROJECT_NAME` | Bedrock project name, e.g. `corpus-query` |
| `AWS_PROJECT_TAG` | Value of the `Project` cost-allocation tag |
| `AWS_BUDGET_EMAIL` | Address that budget alerts are sent to |
| `AWS_BUDGET_LIMIT_USD` | Monthly budget in USD (default `20`) |
| `AWS_PROJECT_ARN` | Written by the creation script; do not set by hand |

### The three steps, in order

Each one needs what the previous one produced.

#### 1. Create the Bedrock project

Bedrock's Projects API is REST-only — no CLI command, no SDK client — so this
is a SigV4-signed request rather than a CDK resource:

```bash
uv run python -m infra.create_project --dry-run  # print the request, send nothing
uv run python -m infra.create_project            # create it
```

The script prints the new project's ARN and id, and writes `AWS_PROJECT_ARN`
into `.env.admin`. Creating a project needs admin credentials; a long-term
Bedrock API key can only get and list projects.

#### 2. Deploy the stack

The stack reads `AWS_PROJECT_ARN` from `.env.admin`, so it will not
synthesize before step 1 has run.

```bash
cdk synth
cdk deploy
```

It creates a customer-managed IAM policy allowing
`bedrock-mantle:CreateInference` on that project ARN alone, and a monthly cost
budget that alerts at 80% of actual spend and at a forecast of 100%. The
policy's ARN is a stack output.

#### 3. Mint the API key

Attach the policy from step 2 to the identity the key belongs to, then create
the Bedrock API key in the console or with the CLI, and hand it over out of
band.

The key is deliberately not created by CloudFormation: its value would be
stored in stack state and in stack outputs, readable by anyone who can
describe the stack.

### Notes

- The SigV4 signing service name (`bedrock-mantle`) is inferred from the ARN
  namespace in the AWS documentation rather than confirmed against a live
  call. If it is wrong, the first real run fails with a signing error that
  names the expected service.
- The budget covers account spend rather than filtering on the `Project` tag.
  Tag-scoped filtering needs the cost allocation tag to be activated in
  Billing, which is console-only; account-wide is what catches runaway spend
  either way.
