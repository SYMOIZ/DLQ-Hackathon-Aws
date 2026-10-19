"""Evidence-based live health check (boto3 + HTTPS). Stdlib urllib + boto3."""
from __future__ import annotations

import json
import re
import secrets
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone

import boto3

REGION = "us-east-1"
PROFILE = "default"
INSTANCE = "<EC2_INSTANCE_ID>"
BASE = "https://<CLOUDFRONT_DOMAIN>"
DIST = "<CLOUDFRONT_DISTRIBUTION_ID>"
STACK = "dlq-judge"
CLIENT = "<COGNITO_CLIENT_ID>"
POOL = "<COGNITO_USER_POOL_ID>"
RESULTS: list[tuple[str, str, str]] = []


def rec(name: str, ok: bool, ev: str) -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", ev[:400]))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {ev[:200]}", flush=True)


def main() -> int:
    sess = boto3.Session(profile_name=PROFILE, region_name=REGION)
    ec2 = sess.client("ec2")
    ssm = sess.client("ssm")
    cfn = sess.client("cloudformation")
    sqs = sess.client("sqs")
    s3 = sess.client("s3")
    cf = sess.client("cloudfront")
    cognito = sess.client("cognito-idp")
    ctx = ssl.create_default_context()

    # EC2
    inst = ec2.describe_instances(InstanceIds=[INSTANCE])["Reservations"][0]["Instances"][0]
    state = inst["State"]["Name"]
    dns = inst.get("PublicDnsName") or ""
    vol = (inst.get("BlockDeviceMappings") or [{}])[0].get("Ebs", {}).get("VolumeId", "")
    rec("ec2_running", state == "running", f"state={state} dns={dns} vol={vol}")

    # SSM
    info = (
        ssm.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [INSTANCE]}]
        ).get("InstanceInformationList")
        or []
    )
    ping = info[0].get("PingStatus") if info else "missing"
    rec("ssm_online", ping == "Online", f"ping={ping}")

    # CFN
    st = cfn.describe_stacks(StackName=STACK)["Stacks"][0]
    rec(
        "cfn_stack",
        st["StackStatus"] in ("CREATE_COMPLETE", "UPDATE_COMPLETE"),
        f"status={st['StackStatus']}",
    )

    # CloudFront origin matches EC2 DNS
    dcfg = cf.get_distribution_config(Id=DIST)
    origin = dcfg["DistributionConfig"]["Origins"]["Items"][0]["DomainName"]
    rec("cf_origin_match", bool(dns) and origin == dns, f"origin={origin} ec2_dns={dns}")

    # SQS queues
    found = []
    for name in [
        "dlqj-orders",
        "dlqj-orders-dlq",
        "dlqj-payments",
        "dlqj-payments-dlq",
        "dlqj-shipping",
        "dlqj-shipping-dlq",
    ]:
        try:
            url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
            attrs = sqs.get_queue_attributes(
                QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"]
            )["Attributes"]
            found.append(f"{name}={attrs.get('ApproximateNumberOfMessages')}")
        except Exception as e:
            found.append(f"{name}=ERR:{e}")
    rec("sqs_queues", all("ERR" not in x for x in found), "; ".join(found))

    # S3
    for b in ["dlqj-quarantine-<AWS_ACCOUNT_ID>", "dlqj-deploy-<AWS_ACCOUNT_ID>"]:
        try:
            s3.head_bucket(Bucket=b)
            n = s3.list_objects_v2(Bucket=b, MaxKeys=5).get("KeyCount", 0)
            rec(f"s3_{b.split('-')[1]}", True, f"bucket={b} sample_keys={n}")
        except Exception as e:
            rec(f"s3_{b.split('-')[1]}", False, str(e))

    # Cognito
    pool = cognito.describe_user_pool(UserPoolId=POOL)["UserPool"]
    rec(
        "cognito_pool",
        pool.get("Id") == POOL,
        f"name={pool.get('Name')} status={pool.get('Status')}",
    )

    # Public HTTPS
    try:
        html = urllib.request.urlopen(BASE + "/", context=ctx, timeout=45).read().decode()
        rec(
            "public_landing",
            'id="site-landing"' in html and "btn-add-aws" in html,
            f"len={len(html)} landing={'site-landing' in html} connector_btn={'btn-add-aws' in html}",
        )
        token = re.search(r'data-token="([^"]+)"', html)
        tok = token.group(1) if token else ""
        rec("csrf_token", bool(tok), f"len={len(tok)}")
    except Exception as e:
        rec("public_landing", False, str(e))
        return 1

    # healthz + public stats
    try:
        hz = urllib.request.urlopen(BASE + "/healthz", context=ctx, timeout=30).read()
        rec("healthz", b'"ok"' in hz, hz[:120].decode())
    except Exception as e:
        rec("healthz", False, str(e))
    try:
        stats = json.loads(
            urllib.request.urlopen(BASE + "/api/public/stats", context=ctx, timeout=30).read()
        )
        rec(
            "public_stats",
            stats.get("has_run") is True and int(stats.get("processed") or 0) > 0,
            json.dumps({k: stats.get(k) for k in ("has_run", "run_id", "queue", "processed", "label")}),
        )
    except Exception as e:
        rec("public_stats", False, str(e))

    # Auth + connector E2E
    email = f"qa.{secrets.token_hex(3)}@example.com"
    pw = "<TEST_PASSWORD>"
    try:
        cognito.sign_up(
            ClientId=CLIENT,
            Username=email,
            Password=pw,
            UserAttributes=[{"Name": "email", "Value": email}],
        )
        req = urllib.request.Request(
            BASE + "/api/auth/login",
            data=json.dumps({"email": email, "password": pw}).encode(),
            headers={"Content-Type": "application/json", "X-DLQJ-Token": tok},
            method="POST",
        )
        login = json.loads(urllib.request.urlopen(req, context=ctx, timeout=45).read())
        id_token = login.get("id_token") or ""
        rec("auth_login", bool(id_token), f"email={email}")
    except Exception as e:
        rec("auth_login", False, str(e))
        id_token = ""

    if id_token:
        h = {
            "X-DLQJ-Token": tok,
            "Authorization": f"Bearer {id_token}",
            "Content-Type": "application/json",
        }
        # 401 without auth
        try:
            urllib.request.urlopen(
                urllib.request.Request(BASE + "/api/run", headers={"X-DLQJ-Token": tok}),
                context=ctx,
                timeout=20,
            )
            rec("api_401", False, "expected 401")
        except urllib.error.HTTPError as e:
            rec("api_401", e.code in (401, 403), f"status={e.code}")

        for path, name in [
            ("/api/run", "api_run"),
            ("/api/messages?page=1&page_size=10", "api_messages"),
            ("/api/clusters", "api_clusters"),
            ("/api/benchmark", "api_benchmark"),
            ("/api/aws/connector", "api_connector"),
        ]:
            try:
                raw = urllib.request.urlopen(
                    urllib.request.Request(BASE + path, headers=h),
                    context=ctx,
                    timeout=60,
                ).read()
                doc = json.loads(raw)
                if name == "api_connector":
                    rec(
                        name,
                        doc.get("account_id") == "<AWS_ACCOUNT_ID>"
                        and doc.get("st_label") in ("Connected", "Degraded"),
                        json.dumps(
                            {
                                k: doc.get(k)
                                for k in ("st_label", "account_id", "queues", "role_name")
                            }
                        ),
                    )
                elif name == "api_run":
                    rec(
                        name,
                        "run_id" in doc,
                        f"run_id={doc.get('run_id')} queue={doc.get('queue')} processed={doc.get('processed')}",
                    )
                else:
                    rec(name, True, f"keys={list(doc)[:8]}")
            except Exception as e:
                rec(name, False, str(e))

        # ARN deny
        try:
            req = urllib.request.Request(
                BASE + "/api/queue",
                data=json.dumps(
                    {"dlq_arn": "arn:aws:sqs:us-east-1:<AWS_ACCOUNT_ID>:prod-secret"}
                ).encode(),
                headers=h,
                method="POST",
            )
            urllib.request.urlopen(req, context=ctx, timeout=20)
            rec("arn_deny", False, "expected 400")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            rec("arn_deny", e.code == 400 and "prefix" in body, body[:120])

        # ARN allow payments
        try:
            req = urllib.request.Request(
                BASE + "/api/queue",
                data=json.dumps(
                    {
                        "dlq_arn": "arn:aws:sqs:us-east-1:<AWS_ACCOUNT_ID>:dlqj-payments-dlq"
                    }
                ).encode(),
                headers=h,
                method="POST",
            )
            body = urllib.request.urlopen(req, context=ctx, timeout=20).read().decode()
            rec("arn_allow", '"ok": true' in body or '"ok":true' in body, body[:160])
        except Exception as e:
            rec("arn_allow", False, str(e))

        # connector test
        try:
            req = urllib.request.Request(
                BASE + "/api/aws/connector/test",
                data=b"{}",
                headers=h,
                method="POST",
            )
            doc = json.loads(urllib.request.urlopen(req, context=ctx, timeout=60).read())
            rec(
                "connector_test",
                doc.get("ok") is True,
                (doc.get("message") or "")[:160],
            )
        except Exception as e:
            rec("connector_test", False, str(e))

        # SSM service status
        cid = ssm.send_command(
            InstanceIds=[INSTANCE],
            DocumentName="AWS-RunShellScript",
            Parameters={
                "commands": [
                    "systemctl is-active dlqj-ui; systemctl is-active dlqj-decider; "
                    "curl -sS http://127.0.0.1:8765/healthz; "
                    "ls /opt/dlq-judge/runs | head -5"
                ]
            },
        )["Command"]["CommandId"]
        import time

        time.sleep(12)
        inv = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
        out = inv.get("StandardOutputContent") or ""
        rec(
            "systemd_services",
            "active" in out and '"ok"' in out,
            out[:300].replace("\n", " | "),
        )

    fails = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    report = [
        "# QA_LIVE_HEALTH.md — Hands-on live QA",
        "",
        f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
        f"URL: `{BASE}` · Instance: `{INSTANCE}` · Region: `{REGION}`",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    for n, s, e in RESULTS:
        report.append(f"| {n} | {s} | `{e.replace('|', '/')}` |")
    report += ["", f"Summary: **{len(RESULTS) - fails}/{len(RESULTS)} PASS**, {fails} FAIL"]
    path = "docs/QA_LIVE_HEALTH.md"
    open(path, "w", encoding="utf-8").write("\n".join(report) + "\n")
    print(f"wrote {path} fails={fails}", flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
