"""Preflight: queue depths, S3 objects, existing run summary."""
from __future__ import annotations

import json

import boto3

REGION = "us-east-1"
ACCOUNT = "<AWS_ACCOUNT_ID>"
session = boto3.Session(profile_name="default", region_name=REGION)
sqs = session.client("sqs")
s3 = session.client("s3")

queues = [
    "dlqj-payments-dlq",
    "dlqj-payments",
    "dlqj-orders-dlq",
    "dlqj-shipping-dlq",
]
for name in queues:
    url = f"https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/{name}"
    attrs = sqs.get_queue_attributes(
        QueueUrl=url,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
            "ApproximateNumberOfMessagesDelayed",
        ],
    )["Attributes"]
    print(f"{name}: {json.dumps(attrs)}", flush=True)

# S3 quarantine sample
bucket = f"dlqj-quarantine-{ACCOUNT}"
resp = s3.list_objects_v2(Bucket=bucket, MaxKeys=20)
print(f"s3://{bucket} KeyCount={resp.get('KeyCount')} contents={[o['Key'] for o in resp.get('Contents', [])][:15]}", flush=True)

deploy = f"dlqj-deploy-{ACCOUNT}"
resp2 = s3.list_objects_v2(Bucket=deploy, Prefix="app/", MaxKeys=10)
print(f"s3://{deploy}/app KeyCount={resp2.get('KeyCount')} keys={[o['Key'] for o in resp2.get('Contents', [])]}", flush=True)
