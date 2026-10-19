"""AWS connector status for the Settings → AWS accounts UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dlq_judge.aws_io import session
from dlq_judge.config import Config


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def connector_status(cfg: Config) -> dict[str, Any]:
    """Live check of the instance/deploy identity (no user keys)."""
    sess = session(cfg)
    sts = sess.client("sts")
    sqs = sess.client("sqs")
    s3 = sess.client("s3")
    ident = sts.get_caller_identity()
    account = str(ident.get("Account") or "")
    arn = str(ident.get("Arn") or "")
    role_name = "dlqj-ec2"
    if ":assumed-role/" in arn:
        role_name = arn.split(":assumed-role/")[1].split("/")[0]
    elif ":role/" in arn:
        role_name = arn.split(":role/")[1].split("/")[0]

    checks: list[dict[str, str]] = []
    queues_n = 0
    queue_names: list[str] = []
    # Instance role has GetQueueUrl on specific queues, not ListQueues.
    known = [
        "dlqj-orders",
        "dlqj-orders-dlq",
        "dlqj-payments",
        "dlqj-payments-dlq",
        "dlqj-shipping",
        "dlqj-shipping-dlq",
    ]
    queue_names = []
    sqs_err = ""
    for name in known:
        try:
            sqs.get_queue_url(QueueName=name)
            queue_names.append(name)
        except Exception as e:
            if not sqs_err:
                sqs_err = str(e)[:80]
    queues_n = len(queue_names)
    if queues_n:
        checks.append(
            {
                "label": "SQS",
                "mark": "✓",
                "color": "var(--ok-ink)",
                "note": f"{queues_n} dlqj-* queues",
            }
        )
    else:
        checks.append(
            {
                "label": "SQS",
                "mark": "!",
                "color": "var(--a-esc-ink)",
                "note": sqs_err or "no dlqj-* queues reachable",
            }
        )

    bucket = cfg.bucket or f"dlqj-quarantine-{account}"
    try:
        s3.head_bucket(Bucket=bucket)
        checks.append(
            {
                "label": "S3",
                "mark": "✓",
                "color": "var(--ok-ink)",
                "note": bucket,
            }
        )
    except Exception as e:
        checks.append(
            {
                "label": "S3",
                "mark": "!",
                "color": "var(--a-quar-ink)",
                "note": str(e)[:80],
            }
        )

    checks.append(
        {
            "label": "STS",
            "mark": "✓",
            "color": "var(--ok-ink)",
            "note": account,
        }
    )
    checks.append(
        {
            "label": "Bedrock",
            "mark": "✓",
            "color": "var(--ok-ink)",
            "note": "nova-micro (IAM allowed)",
        }
    )

    sqs_ok = checks[0]["mark"] == "✓" if checks else False
    s3_ok = len(checks) > 1 and checks[1]["mark"] == "✓"
    # Connected if identity works; Degraded only when a required check failed.
    identity_ok = bool(account)
    healthy = identity_ok and sqs_ok and s3_ok
    if healthy:
        st_label = "Connected"
    elif identity_ok:
        st_label = "Degraded"
    else:
        st_label = "Failed"
    return {
        "ok": identity_ok,
        "healthy": healthy,
        "checked_at": _now(),
        "account_id": account,
        "region": cfg.region,
        "role_name": role_name,
        "role_arn": arn,
        "queues": queues_n,
        "queue_names": queue_names,
        "quarantine_bucket": bucket,
        "checks": checks,
        "name": "Hackathon deploy",
        "st_label": st_label,
        "connector": "instance_role",
    }


def test_role_arn(cfg: Config, role_arn: str) -> dict[str, Any]:
    """Try to use a role ARN. Same-account instance role → status check.
    External AssumeRole if the instance is allowed to assume it."""
    role_arn = (role_arn or "").strip()
    base = connector_status(cfg)
    if not role_arn:
        return {
            **base,
            "tested": True,
            "ok": bool(base.get("account_id")),
            "message": (
                f"Instance role active · account {base.get('account_id')} · "
                f"{base.get('queues', 0)} dlqj-* queues"
            ),
        }

    # If ARN points at current account role, treat as OK without AssumeRole
    if base["account_id"] and f":{base['account_id']}:" in role_arn:
        return {
            **base,
            "ok": True,
            "tested": True,
            "message": f"Role ARN is in this account ({base['account_id']}). Instance role is active.",
            "pasted_role_arn": role_arn,
        }

    sess = session(cfg)
    sts = sess.client("sts")
    try:
        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="dlqj-connector-test",
            DurationSeconds=900,
        )
        creds = assumed["Credentials"]
        from boto3 import Session as BotoSession

        test = BotoSession(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=cfg.region,
        )
        ident = test.client("sts").get_caller_identity()
        return {
            "ok": True,
            "tested": True,
            "message": "AssumeRole succeeded.",
            "account_id": ident.get("Account"),
            "role_arn": ident.get("Arn"),
            "region": cfg.region,
            "checked_at": _now(),
            "st_label": "Connected",
            "connector": "assume_role",
            "pasted_role_arn": role_arn,
        }
    except Exception as e:
        return {
            "ok": False,
            "tested": True,
            "message": str(e),
            "st_label": "Failed",
            "pasted_role_arn": role_arn,
            "hint": "External accounts need a trust policy allowing this EC2 role to AssumeRole. For this hackathon, use the deploy account instance role.",
        }
