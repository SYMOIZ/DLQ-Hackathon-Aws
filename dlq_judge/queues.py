"""Queue ARN allowlist: same account/region, name starts with dlqj-."""

from __future__ import annotations

import re
from dataclasses import dataclass

_ARN = re.compile(
    r"^arn:aws:sqs:(?P<region>[a-z0-9-]+):(?P<account>\d{12}):(?P<name>[A-Za-z0-9_-]+)$"
)


class QueueArnError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedQueueArn:
    region: str
    account: str
    name: str
    arn: str

    @property
    def url(self) -> str:
        return f"https://sqs.{self.region}.amazonaws.com/{self.account}/{self.name}"


def parse_and_validate(
    arn: str,
    *,
    expected_account: str,
    expected_region: str,
    prefix: str = "dlqj-",
) -> ParsedQueueArn:
    m = _ARN.match((arn or "").strip())
    if not m:
        raise QueueArnError("invalid_arn")
    region, account, name = m.group("region"), m.group("account"), m.group("name")
    if account != expected_account:
        raise QueueArnError("wrong_account")
    if region != expected_region:
        raise QueueArnError("wrong_region")
    if not name.startswith(prefix):
        raise QueueArnError("prefix_denied")
    return ParsedQueueArn(region=region, account=account, name=name, arn=arn.strip())
