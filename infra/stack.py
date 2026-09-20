"""CDK stack holding the IAM policy and the budget alarm.

The IAM policy scopes inference permission to the one model this project
calls, and to nothing else. Both ARNs it names are built from CDK's own
account and region tokens rather than read from configuration, so no account
id is written down anywhere in the repository.

The policy is attached here rather than by hand, to the identity named by
``AWS_INFERENCE_USER``. That identity is not created here: it owns the
Bedrock API key, which outlives any one version of the policy.

The Bedrock API key itself is deliberately not here. CloudFormation would
keep its value in stack state and outputs, so it is minted out of band once
this stack is deployed.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Environment, Stack, Tags
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_iam as iam
from constructs import Construct

from infra.config import PROJECT_TAG_KEY, read_number, require

#: Actions that run inference. The streaming one is not optional: transcript
#: generation streams its response, because a batch of them takes long enough
#: that the SDK refuses to wait for it in one piece.
INFERENCE_ACTIONS = (
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream",
)

#: The inference profile the scripts call, which must match the ``MODEL``
#: they hardcode. A profile rather than a plain model id, because that is how
#: the model is offered.
INFERENCE_PROFILE_ID = "us.anthropic.claude-sonnet-4-6"

#: The foundation model that profile resolves to. The ``us.`` prefix belongs
#: to the profile; the model behind it does not carry one.
FOUNDATION_MODEL_ID = "anthropic.claude-sonnet-4-6"

#: Action that permits presenting a Bedrock API key at all. It authorizes the
#: credential rather than the call, which is why it is evaluated against ``*``
#: rather than against a model: an identity holding this and nothing else can
#: still run no inference anywhere. Inference stays scoped by
#: :data:`INFERENCE_ACTIONS` on the two ARNs below. Calls made with ordinary
#: SigV4 credentials never need it, which is why it is easy to leave out and
#: only shows up as a 403 on the first call made with a key.
BEARER_TOKEN_ACTION = "bedrock:CallWithBearerToken"

#: Percentage of the budget at which spend so far raises an alert.
ACTUAL_ALERT_THRESHOLD = 80

#: Percentage of the budget at which the month's forecast raises an alert.
FORECAST_ALERT_THRESHOLD = 100

_DEFAULT_BUDGET_LIMIT_USD = 20.0


class CorpusQueryStack(Stack):
    """Inference permission scoped to one model, plus a budget."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_values: dict[str, str],
        **kwargs: object,
    ) -> None:
        """Define the stack.

        Args:
            scope: Enclosing construct, normally the CDK app.
            construct_id: Identifier of this stack within the app.
            env_values: Settings as returned by :func:`infra.config.load_env`.
            **kwargs: Passed through to :class:`aws_cdk.Stack`.

        Raises:
            ConfigError: If a required setting is missing.
        """
        super().__init__(scope, construct_id, **kwargs)

        project_name = require(env_values, "AWS_PROJECT_NAME")
        inference_user = require(env_values, "AWS_INFERENCE_USER")
        notification_email = require(env_values, "AWS_BUDGET_EMAIL")
        budget_limit = read_number(
            env_values, "AWS_BUDGET_LIMIT_USD", _DEFAULT_BUDGET_LIMIT_USD
        )

        Tags.of(self).add(PROJECT_TAG_KEY, require(env_values, "AWS_PROJECT_TAG"))

        # The name is deliberately left to CloudFormation. A managed policy's
        # description and path are immutable, so changing either means
        # replacing the policy — and CloudFormation refuses to replace one
        # whose name is pinned, because the replacement it would create
        # collides with the original. A pinned name therefore freezes both
        # fields permanently, and an edit to one fails the deploy with a
        # duplicate-name error, taking the policy document down with it. A
        # generated name costs a readable entry in the IAM console; the
        # policy is found by the ARN this stack outputs.
        self.inference_policy = iam.ManagedPolicy(
            self,
            "InferencePolicy",
            description=(
                f"Run inference as {project_name} against one model, and nothing else."
            ),
            # Attaching here rather than by hand is what makes a replacement
            # survivable: CloudFormation attaches the new policy before it
            # deletes the old one, so the API key never loses permission and
            # nobody has to remember to re-attach it.
            users=[iam.User.from_user_name(self, "InferenceUser", inference_user)],
            statements=[
                iam.PolicyStatement(
                    sid="RunInferenceOnOneModel",
                    effect=iam.Effect.ALLOW,
                    actions=list(INFERENCE_ACTIONS),
                    resources=[
                        self.format_arn(
                            service="bedrock",
                            resource="inference-profile",
                            resource_name=INFERENCE_PROFILE_ID,
                        ),
                        # The profile is the thing called, but a cross-region
                        # one is granted on the model it routes to as well,
                        # in every region it can route to — which is why this
                        # ARN wildcards the region and names no account.
                        self.format_arn(
                            service="bedrock",
                            region="*",
                            account="",
                            resource="foundation-model",
                            resource_name=FOUNDATION_MODEL_ID,
                        ),
                    ],
                ),
                iam.PolicyStatement(
                    sid="UseApiKey",
                    effect=iam.Effect.ALLOW,
                    actions=[BEARER_TOKEN_ACTION],
                    resources=["*"],
                ),
            ],
        )

        self.budget = budgets.CfnBudget(
            self,
            "SpendBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"{project_name}-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=budget_limit, unit="USD"
                ),
            ),
            notifications_with_subscribers=[
                _alert(
                    "ACTUAL",
                    ACTUAL_ALERT_THRESHOLD,
                    notification_email,
                ),
                _alert(
                    "FORECASTED",
                    FORECAST_ALERT_THRESHOLD,
                    notification_email,
                ),
            ],
        )

        CfnOutput(
            self,
            "InferencePolicyArn",
            value=self.inference_policy.managed_policy_arn,
            description=f"The policy attached to {inference_user}.",
        )


def _alert(
    notification_type: str, threshold: int, email: str
) -> budgets.CfnBudget.NotificationWithSubscribersProperty:
    """Build one budget notification and its single email subscriber.

    Args:
        notification_type: ``ACTUAL`` for spend so far, ``FORECASTED`` for the
            projected month-end total.
        threshold: Percentage of the budget that triggers the alert.
        email: Address the alert is sent to.

    Returns:
        The notification, ready to attach to the budget.
    """
    return budgets.CfnBudget.NotificationWithSubscribersProperty(
        notification=budgets.CfnBudget.NotificationProperty(
            comparison_operator="GREATER_THAN",
            notification_type=notification_type,
            threshold=threshold,
            threshold_type="PERCENTAGE",
        ),
        subscribers=[
            budgets.CfnBudget.SubscriberProperty(
                address=email, subscription_type="EMAIL"
            )
        ],
    )


def stack_environment(env_values: dict[str, str], account: str | None) -> Environment:
    """Return the CDK environment the stack deploys into.

    Args:
        env_values: Settings as returned by :func:`infra.config.load_env`.
        account: Account id, normally from ``CDK_DEFAULT_ACCOUNT``. ``None``
            leaves the stack account-agnostic, which is enough to synthesize.

    Returns:
        The target account and region.
    """
    return Environment(account=account, region=require(env_values, "AWS_REGION"))
