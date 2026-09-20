"""Tests for the synthesized CloudFormation template."""

from __future__ import annotations

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from infra.config import ConfigError
from infra.stack import CorpusQueryStack

PROJECT_ARN = "arn:aws:bedrock-mantle:us-east-1:111111111111:project/abc123"

SETTINGS = {
    "AWS_REGION": "us-east-1",
    "AWS_PROJECT_NAME": "corpus-query",
    "AWS_PROJECT_TAG": "corpus-query",
    "AWS_PROJECT_ARN": PROJECT_ARN,
    "AWS_BUDGET_EMAIL": "alerts@example.com",
    "AWS_BUDGET_LIMIT_USD": "25",
}


def synthesize(settings: dict[str, str]) -> Template:
    app = cdk.App()
    stack = CorpusQueryStack(app, "TestStack", env_values=settings)
    return Template.from_stack(stack)


@pytest.fixture
def template() -> Template:
    return synthesize(SETTINGS)


def test_policy_allows_inference_on_the_project_and_nothing_else(template: Template):
    template.resource_count_is("AWS::IAM::ManagedPolicy", 1)
    template.has_resource_properties(
        "AWS::IAM::ManagedPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": [
                        {
                            "Action": "bedrock-mantle:CreateInference",
                            "Effect": "Allow",
                            "Resource": PROJECT_ARN,
                            "Sid": "RunInferenceInProject",
                        }
                    ]
                }
            )
        },
    )


def test_budget_carries_a_limit_and_an_email_notification(template: Template):
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {
            "Budget": Match.object_like(
                {
                    "BudgetType": "COST",
                    "TimeUnit": "MONTHLY",
                    "BudgetLimit": {"Amount": 25, "Unit": "USD"},
                }
            ),
            "NotificationsWithSubscribers": Match.array_with(
                [
                    Match.object_like(
                        {
                            "Notification": {
                                "ComparisonOperator": "GREATER_THAN",
                                "NotificationType": "ACTUAL",
                                "Threshold": 80,
                                "ThresholdType": "PERCENTAGE",
                            },
                            "Subscribers": [
                                {
                                    "Address": "alerts@example.com",
                                    "SubscriptionType": "EMAIL",
                                }
                            ],
                        }
                    )
                ]
            ),
        },
    )


def test_budget_also_alerts_on_the_forecast(template: Template):
    budgets = template.find_resources("AWS::Budgets::Budget")
    (budget,) = budgets.values()
    types = [
        entry["Notification"]["NotificationType"]
        for entry in budget["Properties"]["NotificationsWithSubscribers"]
    ]
    assert types == ["ACTUAL", "FORECASTED"]


def test_budget_limit_defaults_when_unset():
    settings = {k: v for k, v in SETTINGS.items() if k != "AWS_BUDGET_LIMIT_USD"}
    template = synthesize(settings)
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {"Budget": Match.object_like({"BudgetLimit": {"Amount": 20, "Unit": "USD"}})},
    )


def test_stack_refuses_to_synthesize_before_the_project_exists():
    settings = {k: v for k, v in SETTINGS.items() if k != "AWS_PROJECT_ARN"}
    with pytest.raises(ConfigError, match="AWS_PROJECT_ARN"):
        synthesize(settings)
