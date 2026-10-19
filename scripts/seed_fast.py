"""Fast seed: cache queue URL, reuse boto3 client."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3

from dlq_judge.config import get_config


def main() -> int:
    cfg = get_config(reload=True)
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    force = "--force" in sys.argv
    sess = boto3.Session(profile_name=cfg.aws_profile, region_name=cfg.region)
    sqs = sess.client("sqs")
    url = sqs.get_queue_url(QueueName=cfg.dlq)["QueueUrl"]
    attrs = sqs.get_queue_attributes(
        QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"]
    )["Attributes"]
    depth = int(attrs.get("ApproximateNumberOfMessages", 0))
    print(f"depth_before={depth}", flush=True)
    if depth > 0 and not force:
        print("refused", flush=True)
        return 1
    lines = [
        ln
        for ln in Path("bench/dataset/messages.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ][:count]
    for i, ln in enumerate(lines, 1):
        obj = json.loads(ln)
        body = obj["body"] if isinstance(obj["body"], str) else json.dumps(obj["body"])
        raw = dict(obj.get("attributes") or {})
        if "fixture_id" not in raw and obj.get("fixture_id"):
            raw["fixture_id"] = obj["fixture_id"]
        msg_attrs = {
            k: {"DataType": "String", "StringValue": str(v)} for k, v in raw.items()
        }
        sqs.send_message(QueueUrl=url, MessageBody=body, MessageAttributes=msg_attrs)
        if i % 20 == 0 or i == len(lines):
            print(f"seeded {i}/{len(lines)}", flush=True)
    depth2 = int(
        sqs.get_queue_attributes(
            QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"]
        )["Attributes"].get("ApproximateNumberOfMessages", 0)
    )
    print(f"depth_after={depth2}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
