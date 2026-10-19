"""Layer 2: SQS/S3 wrappers and queue allowlist (FR-17)."""

from __future__ import annotations

import json
from typing import Any

import boto3

from dlq_judge.config import Config


class QueueNotAllowed(Exception):
    pass


_SESSION = None
_SESSION_KEY: tuple[str, str] | None = None


def session(cfg: Config):
    global _SESSION, _SESSION_KEY
    profile = cfg.aws_profile or None
    key = (profile or "", cfg.region)
    if _SESSION is None or _SESSION_KEY != key:
        if profile:
            _SESSION = boto3.Session(profile_name=profile, region_name=cfg.region)
        else:
            _SESSION = boto3.Session(region_name=cfg.region)
        _SESSION_KEY = key
    return _SESSION


def assert_allowed(name: str, prefix: str) -> None:
    if not name.startswith(prefix):
        raise QueueNotAllowed(f"queue {name!r} not allowed (prefix {prefix!r})")


def queue_url(cfg: Config, name: str) -> str:
    assert_allowed(name, cfg.queue_prefix)
    sqs = session(cfg).client("sqs")
    return sqs.get_queue_url(QueueName=name)["QueueUrl"]


def receive_batch(cfg: Config, queue_name: str, max_messages: int = 10, visibility: int = 300) -> list[dict]:
    url = queue_url(cfg, queue_name)
    sqs = session(cfg).client("sqs")
    resp = sqs.receive_message(
        QueueUrl=url,
        MaxNumberOfMessages=min(10, max_messages),
        WaitTimeSeconds=1,
        VisibilityTimeout=visibility,
        MessageAttributeNames=["All"],
        AttributeNames=["All"],
    )
    return resp.get("Messages") or []


def send_message(
    cfg: Config,
    queue_name: str,
    body: str,
    attributes: dict[str, Any] | None = None,
    delay_seconds: int = 0,
) -> str:
    url = queue_url(cfg, queue_name)
    sqs = session(cfg).client("sqs")
    kwargs: dict[str, Any] = {"QueueUrl": url, "MessageBody": body}
    if delay_seconds:
        kwargs["DelaySeconds"] = delay_seconds
    if attributes:
        msg_attrs = {}
        for k, v in attributes.items():
            if isinstance(v, dict) and ("StringValue" in v or "DataType" in v):
                msg_attrs[k] = v
            else:
                msg_attrs[k] = {"DataType": "String", "StringValue": str(v)}
        kwargs["MessageAttributes"] = msg_attrs
    return sqs.send_message(**kwargs)["MessageId"]


def delete_message(cfg: Config, queue_name: str, receipt_handle: str) -> None:
    url = queue_url(cfg, queue_name)
    session(cfg).client("sqs").delete_message(QueueUrl=url, ReceiptHandle=receipt_handle)


def change_visibility(cfg: Config, queue_name: str, receipt_handle: str, timeout: int) -> None:
    url = queue_url(cfg, queue_name)
    session(cfg).client("sqs").change_message_visibility(
        QueueUrl=url, ReceiptHandle=receipt_handle, VisibilityTimeout=timeout
    )


def approx_depth(cfg: Config, queue_name: str) -> int:
    url = queue_url(cfg, queue_name)
    attrs = session(cfg).client("sqs").get_queue_attributes(
        QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"]
    )["Attributes"]
    return int(attrs.get("ApproximateNumberOfMessages", 0))


def s3_put_json(cfg: Config, key: str, obj: dict) -> None:
    bucket = cfg.bucket
    if not bucket:
        raise RuntimeError("DLQJ_BUCKET not set")
    session(cfg).client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(obj).encode("utf-8"),
        ContentType="application/json",
    )


def s3_get_json(cfg: Config, key: str) -> dict:
    bucket = cfg.bucket
    if not bucket:
        raise RuntimeError("DLQJ_BUCKET not set")
    raw = session(cfg).client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(raw.decode("utf-8"))


def stack_outputs(cfg: Config) -> dict[str, str]:
    cfn = session(cfg).client("cloudformation")
    stacks = cfn.describe_stacks(StackName=cfg.stack_name)["Stacks"]
    outs = stacks[0].get("Outputs") or []
    return {o["OutputKey"]: o["OutputValue"] for o in outs}
