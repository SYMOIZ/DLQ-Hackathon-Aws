import pytest

from dlq_judge.queues import QueueArnError, parse_and_validate

# Synthetic 12-digit account for unit tests only (not a real deploy account).
_ACCT = "123456789012"


def test_ok():
    p = parse_and_validate(
        f"arn:aws:sqs:us-east-1:{_ACCT}:dlqj-orders-dlq",
        expected_account=_ACCT,
        expected_region="us-east-1",
    )
    assert p.name == "dlqj-orders-dlq"


def test_prefix_denied():
    with pytest.raises(QueueArnError, match="prefix_denied"):
        parse_and_validate(
            f"arn:aws:sqs:us-east-1:{_ACCT}:prod-orders",
            expected_account=_ACCT,
            expected_region="us-east-1",
        )


def test_wrong_account():
    with pytest.raises(QueueArnError, match="wrong_account"):
        parse_and_validate(
            "arn:aws:sqs:us-east-1:000000000000:dlqj-x",
            expected_account=_ACCT,
            expected_region="us-east-1",
        )
