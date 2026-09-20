"""Infrastructure for the corpus-query application.

The pieces here provision the AWS resources inference runs against: the CDK
stack holding the scoped IAM policy and the budget alarm (``stack``), and the
settings both it and the scripts read (``config``).
"""
