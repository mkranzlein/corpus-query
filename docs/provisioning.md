# Provisioning

The AWS setup behind the Bedrock calls: an IAM policy that permits inference
against one model and nothing else, and a budget that stops spending when it
runs away. This is a record of how the account was set up, kept for anyone who
needs to reproduce, audit, or extend it.

Nothing here is needed to run the application. Querying reaches no network
service at all, and the corpus that ships with the repository was built before
any of this became a question for a reader. Building a corpus of your own
needs a key, and this page is where that key comes from.

## Credentials for the corpus scripts

The scripts that call a model read their settings from `.env`:
`AWS_BEARER_TOKEN_BEDROCK`, a Bedrock API key, and `AWS_REGION`. This is a
different file from the `.env.admin` the provisioning itself uses.

The model is named as the US cross-region inference profile,
`us.anthropic.claude-sonnet-4-6`, which is how it is offered: a call is routed
to whichever US region has capacity for it. Before spending anything on a
corpus, prove the credentials and the model id line up:

```bash
uv run scripts/bedrock_smoke_test.py   # billed, but one short call
```

## Requirements

- Python 3.14 and [uv](https://docs.astral.sh/uv/)
- The [AWS CDK CLI](https://docs.aws.amazon.com/cdk/v2/guide/cli.html)
  (`npm install -g aws-cdk`), which runs the app through `uv` for you
- AWS credentials for an identity that can create IAM policies and budgets
- An IAM user for the application to call as, which the Bedrock API key is
  minted against. It is not created here: it outlives any one version of the
  policy, and it holds a credential CloudFormation should never see.
- Model access for Claude Sonnet 4.6 enabled in the target region, which is
  granted per account in the Bedrock console
- The target account and region [bootstrapped for
  CDK](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html)
  (`cdk bootstrap`), if they have not been already

## Configuration

Settings live in `.env.admin`, which is gitignored and never committed.
Anything exported in the shell overrides the file.

| Setting | Meaning |
| --- | --- |
| `AWS_REGION` | Region the stack lives in |
| `AWS_PROJECT_NAME` | Prefix for the budget name, e.g. `corpus-query` |
| `AWS_PROJECT_TAG` | Value of the `Project` cost-allocation tag |
| `AWS_INFERENCE_USER` | Existing IAM user the policy is attached to |
| `AWS_BUDGET_EMAIL` | Address that budget alerts are sent to |
| `AWS_BUDGET_LIMIT_USD` | Monthly budget in USD (default `20`) |

No account id appears here, or anywhere else in the repository. The stack
builds the ARNs it grants on from CDK's own account and region tokens.

## The two steps, in order

## 1. Deploy the stack

```bash
cdk synth
cdk deploy
```

It creates a customer-managed IAM policy, attaches it to `AWS_INFERENCE_USER`,
and creates a monthly cost budget that alerts at 80% of actual spend and at a
forecast of 100%. The policy's ARN is a stack output.

At 100% of actual spend the budget also acts: it attaches a second managed
policy, which denies every `bedrock:*` action, to `AWS_INFERENCE_USER`. An
explicit deny outranks the inference grant, so the key stops working until
the deny policy is detached. The stack creates that policy but never attaches
it, and the execution role it hands to the budget can attach or detach that one
policy on that one user and nothing else. AWS reports cost with a delay of
several hours, so this bounds spend rather than stopping it at the exact
dollar.

The policy carries two statements. The first allows `bedrock:InvokeModel` and
`bedrock:InvokeModelWithResponseStream` on two ARNs and nothing else: the
inference profile the scripts name, and the foundation model behind it. The
second ARN is needed because a cross-region profile is only half the grant —
the call is authorized against the model in whichever region it lands in, so
that ARN wildcards the region and names no account. The streaming action is
not optional either: a batch of transcripts is long enough that it has to be
streamed.

The second statement allows `bedrock:CallWithBearerToken` on `*`. It is what
permits presenting an API key at all, and it authorizes the credential rather
than any particular call, which is why it cannot be scoped to a model. An
identity holding only that statement can run no inference anywhere. Callers
using ordinary SigV4 credentials never need it, so it is easy to leave out —
the symptom is a 403 naming the action on the first call made with a key.

Keeping the grant this narrow is the point. An identity holding this policy
can call one model, and cannot enumerate, invoke, or spend against anything
else in Bedrock.

The policy is left unnamed on purpose. A managed policy's description and path
are immutable, so changing either means replacing the policy — and
CloudFormation refuses to replace one whose name is pinned, because the
replacement collides with the original. Naming it would freeze those fields for
good and turn an edit to one of them into a failed deploy that takes the policy
document with it. The attachment lives here for the same reason: on a
replacement CloudFormation attaches the new policy before deleting the old, so
the API key never loses permission and nobody has to re-attach it by hand.

## 2. Mint the API key

Create the Bedrock API key against `AWS_INFERENCE_USER` in the console or with
the CLI, and hand it over out of band. The policy is already attached by step
1, so there is nothing to wire up.

The key is deliberately not created by CloudFormation: its value would be
stored in stack state and in stack outputs, readable by anyone who can
describe the stack.

## Notes

- The model id is hardcoded in three scripts and in the stack, rather than
  configured. A test asserts the four agree, because the failure they would
  otherwise produce is an access denial on the first billed call.
- The budget covers account spend rather than filtering on the `Project` tag.
  Tag-scoped filtering needs the cost allocation tag to be activated in
  Billing, which is console-only; account-wide is what catches runaway spend
  either way.
