"""Infrastructure for the corpus-query application.

The pieces here provision the AWS resources inference runs against: the
Bedrock project that inference is attributed to (``create_project``) and the
CDK stack holding the scoped IAM policy and the budget alarm (``stack``).
"""
