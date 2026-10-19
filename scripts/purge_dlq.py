"""Drain DLQ by receive+delete (hackathon synthetic data only)."""
from __future__ import annotations

import boto3

from dlq_judge.config import get_config


def main() -> None:
    cfg = get_config(reload=True)
    sqs = boto3.Session(profile_name=cfg.aws_profile, region_name=cfg.region).client("sqs")
    url = sqs.get_queue_url(QueueName=cfg.dlq)["QueueUrl"]
    deleted = 0
    empty = 0
    while empty < 5:
        resp = sqs.receive_message(
            QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=1, VisibilityTimeout=30
        )
        msgs = resp.get("Messages") or []
        if not msgs:
            empty += 1
            continue
        empty = 0
        for m in msgs:
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            deleted += 1
        if deleted % 50 == 0:
            print(f"deleted {deleted}", flush=True)
    print(f"done deleted={deleted}", flush=True)


if __name__ == "__main__":
    main()
