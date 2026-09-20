"""Tests for the synthesized CloudFormation template."""

from __future__ import annotations

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from infra.config import ConfigError
from infra.stack import FOUNDATION_MODEL_ID, INFERENCE_PROFILE_ID, CorpusQueryStack

SETTINGS = {
    "AWS_REGION": "us-east-1",
    "AWS_PROJECT_NAME": "corpus-query",
    "AWS_PROJECT_TAG": "corpus-query",
    "AWS_INFERENCE_USER": "corpus-query-inference",
    "AWS_BUDGET_EMAIL": "alerts@example.com",
    "AWS_BUDGET_LIMIT_USD": "25",
}

#: The profile ARN as CloudFormation renders it. The stack builds it from the
#: account and region of whatever it is deployed into rather than from a
#: setting, so what lands in the template is a join around two pseudo
#: parameters rather than a literal.
PROFILE_ARN = {
    "Fn::Join": [
        "",
        [
            "arn:",
            {"Ref": "AWS::Partition"},
            ":bedrock:",
            {"Ref": "AWS::Region"},
            ":",
            {"Ref": "AWS::AccountId"},
            f":inference-profile/{INFERENCE_PROFILE_ID}",
        ],
    ]
}

#: The foundation-model ARN, which names no account and wildcards the region:
#: a cross-region profile routes to the model wherever there is capacity.
MODEL_ARN = {
    "Fn::Join": [
        "",
        [
            "arn:",
            {"Ref": "AWS::Partition"},
            f":bedrock:*::foundation-model/{FOUNDATION_MODEL_ID}",
        ],
    ]
}


def synthesize(settings: dict[str, str]) -> Template:
    app = cdk.App()
    stack = CorpusQueryStack(app, "TestStack", env_values=settings)
    return Template.from_stack(stack)


@pytest.fixture
def template() -> Template:
    return synthesize(SETTINGS)


def test_policy_allows_inference_on_one_model_and_nothing_else(template: Template):
    """Two statements, and the one on ``*`` cannot run inference by itself.

    Presenting an API key needs the credential authorized as well as the
    call, and the credential half cannot be scoped to a model. The literal
    statement list is asserted rather than matched loosely, so a third
    statement — or a widened resource on the inference half, which is the
    whole point of scoping it to a profile — fails here.
    """
    template.resource_count_is("AWS::IAM::ManagedPolicy", 2)
    template.has_resource_properties(
        "AWS::IAM::ManagedPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": [
                        {
                            "Action": [
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream",
                            ],
                            "Effect": "Allow",
                            "Resource": [PROFILE_ARN, MODEL_ARN],
                            "Sid": "RunInferenceOnOneModel",
                        },
                        {
                            "Action": "bedrock:CallWithBearerToken",
                            "Effect": "Allow",
                            "Resource": "*",
                            "Sid": "UseApiKey",
                        },
                    ]
                }
            )
        },
    )


def test_the_policy_attaches_itself_to_the_key_identity(template: Template):
    """Attached by the stack, not by hand.

    This is what lets the policy be replaced: CloudFormation attaches the
    new one before deleting the old, so the API key keeps working across a
    change to an immutable field.
    """
    template.has_resource_properties(
        "AWS::IAM::ManagedPolicy",
        Match.object_like({"Users": ["corpus-query-inference"]}),
    )


def test_the_policy_name_is_left_to_cloudformation(template: Template):
    """A pinned name would freeze the description and path forever.

    CloudFormation cannot replace a named managed policy — the replacement
    collides with the original — and both of those fields can only change by
    replacement. Naming it is therefore a one-way door, so it is not named.
    """
    for policy in template.find_resources("AWS::IAM::ManagedPolicy").values():
        assert "ManagedPolicyName" not in policy["Properties"]


def test_stack_refuses_to_synthesize_without_an_identity_to_attach_to():
    settings = {k: v for k, v in SETTINGS.items() if k != "AWS_INFERENCE_USER"}
    with pytest.raises(ConfigError, match="AWS_INFERENCE_USER"):
        synthesize(settings)


def test_the_policy_names_the_model_the_scripts_call():
    """The grant and the scripts have to agree, and nothing checks that but this.

    Both hardcode the model id, in different files, for different reasons —
    a script cannot read the stack, and the stack is not deployed from the
    script. A mismatch shows up as an access denial on the first billed call.
    """
    from scripts import bedrock_smoke_test, enrich, generate_transcripts

    called = {
        bedrock_smoke_test.MODEL,
        enrich.MODEL,
        generate_transcripts.MODEL,
    }
    assert called == {INFERENCE_PROFILE_ID}
    assert INFERENCE_PROFILE_ID.endswith(FOUNDATION_MODEL_ID.split("anthropic.")[-1])


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


def test_going_over_budget_attaches_a_deny_policy_to_the_user(template: Template):
    template.has_resource_properties(
        "AWS::Budgets::BudgetsAction",
        {
            "BudgetName": "corpus-query-monthly",
            "NotificationType": "ACTUAL",
            "ActionType": "APPLY_IAM_POLICY",
            "ActionThreshold": {"Type": "PERCENTAGE", "Value": 100},
            "ApprovalModel": "AUTOMATIC",
            "Definition": {
                "IamActionDefinition": Match.object_like(
                    {"Users": ["corpus-query-inference"]}
                )
            },
        },
    )


def test_cutoff_policy_denies_bedrock_and_is_not_attached_by_the_stack(
    template: Template,
):
    template.has_resource_properties(
        "AWS::IAM::ManagedPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": [
                        Match.object_like(
                            {
                                "Effect": "Deny",
                                "Action": "bedrock:*",
                                "Resource": "*",
                            }
                        )
                    ]
                }
            ),
            "Users": Match.absent(),
        },
    )


def test_budget_limit_defaults_when_unset():
    settings = {k: v for k, v in SETTINGS.items() if k != "AWS_BUDGET_LIMIT_USD"}
    template = synthesize(settings)
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {"Budget": Match.object_like({"BudgetLimit": {"Amount": 20, "Unit": "USD"}})},
    )


def test_unreadable_budget_limit_names_the_setting():
    settings = {**SETTINGS, "AWS_BUDGET_LIMIT_USD": "twenty dollars"}
    with pytest.raises(ConfigError, match="AWS_BUDGET_LIMIT_USD must be a number"):
        synthesize(settings)


def test_stack_refuses_to_synthesize_without_a_name_to_use():
    settings = {k: v for k, v in SETTINGS.items() if k != "AWS_PROJECT_NAME"}
    with pytest.raises(ConfigError, match="AWS_PROJECT_NAME"):
        synthesize(settings)
