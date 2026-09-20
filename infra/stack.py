"""CDK stack holding the IAM policy and the budget alarm.

The stack depends on the Bedrock project already existing: the IAM policy
scopes inference permission to that project's ARN, which is read from the
environment file rather than committed, because an ARN contains the account
id.

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

#: Action that runs inference through the OpenAI-compatible endpoint. Part of
#: the same ``bedrock-mantle`` namespace as the project ARN.
INFERENCE_ACTION = "bedrock-mantle:CreateInference"

#: Action that permits presenting a Bedrock API key at all. It authorizes the
#: credential rather than the call, which is why it is evaluated against ``*``
#: rather than against a project: an identity holding this and nothing else
#: can still run no inference anywhere. Inference stays scoped by
#: :data:`INFERENCE_ACTION` on the project ARN.
BEARER_TOKEN_ACTION = "bedrock-mantle:CallWithBearerToken"

#: Percentage of the budget at which spend so far raises an alert.
ACTUAL_ALERT_THRESHOLD = 80

#: Percentage of the budget at which the month's forecast raises an alert.
FORECAST_ALERT_THRESHOLD = 100

_DEFAULT_BUDGET_LIMIT_USD = 20.0


class CorpusQueryStack(Stack):
    """Inference permission scoped to one Bedrock project, plus a budget."""

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
            ConfigError: If the project has not been created yet, or another
                required setting is missing.
        """
        super().__init__(scope, construct_id, **kwargs)

        project_arn = require(env_values, "AWS_PROJECT_ARN")
        project_name = require(env_values, "AWS_PROJECT_NAME")
        notification_email = require(env_values, "AWS_BUDGET_EMAIL")
        budget_limit = read_number(
            env_values, "AWS_BUDGET_LIMIT_USD", _DEFAULT_BUDGET_LIMIT_USD
        )

        Tags.of(self).add(PROJECT_TAG_KEY, require(env_values, "AWS_PROJECT_TAG"))

        self.inference_policy = iam.ManagedPolicy(
            self,
            "InferencePolicy",
            managed_policy_name=f"{project_name}-inference",
            description=(
                f"Run inference against the {project_name} Bedrock project, "
                f"and nothing else."
            ),
            statements=[
                iam.PolicyStatement(
                    sid="RunInferenceInProject",
                    effect=iam.Effect.ALLOW,
                    actions=[INFERENCE_ACTION],
                    resources=[project_arn],
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
            description="Attach this to the identity the API key is minted for.",
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
