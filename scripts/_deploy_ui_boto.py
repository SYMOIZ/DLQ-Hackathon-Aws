"""Package UI and deploy via boto3 (no aws CLI)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
REGION = "us-east-1"
PROFILE = "default"
INSTANCE = "<EC2_INSTANCE_ID>"
BUCKET = "dlqj-deploy-<AWS_ACCOUNT_ID>"


def main() -> None:
    sess = boto3.Session(profile_name=PROFILE, region_name=REGION)
    ec2 = sess.client("ec2")
    s3 = sess.client("s3")
    ssm = sess.client("ssm")

    st = ec2.describe_instances(InstanceIds=[INSTANCE])["Reservations"][0]["Instances"][0]
    state = st["State"]["Name"]
    dns = st.get("PublicDnsName") or ""
    print("ec2", state, dns)
    if state != "running":
        print("starting...")
        ec2.start_instances(InstanceIds=[INSTANCE])
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[INSTANCE])
        st = ec2.describe_instances(InstanceIds=[INSTANCE])["Reservations"][0]["Instances"][0]
        dns = st.get("PublicDnsName") or ""
        print("started", dns)
        # wait SSM
        for _ in range(40):
            info = ssm.describe_instance_information(
                Filters=[{"Key": "InstanceIds", "Values": [INSTANCE]}]
            ).get("InstanceInformationList") or []
            ping = info[0].get("PingStatus") if info else None
            print("ssm", ping)
            if ping == "Online":
                break
            time.sleep(8)
        else:
            sys.exit("SSM not online")

    subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "package_app.ps1"),
        ],
        cwd=ROOT,
        check=True,
    )
    tgz = ROOT / "dist" / "dlq-judge-app.tgz"
    s3.upload_file(str(tgz), BUCKET, "app/dlq-judge-app.tgz")
    print("uploaded", tgz.stat().st_size)

    cmds = [
        "set -e",
        f"aws s3 cp s3://{BUCKET}/app/dlq-judge-app.tgz /tmp/a.tgz --region {REGION}",
        "tar -xzf /tmp/a.tgz -C /opt/dlq-judge",
        "/opt/dlq-judge/.venv/bin/pip install -e /opt/dlq-judge -q",
        "systemctl restart dlqj-ui",
        "sleep 2",
        "systemctl is-active dlqj-ui",
        "curl -sS http://127.0.0.1:8765/healthz",
        "grep -c site-landing /opt/dlq-judge/dlq_judge/ui/index.html || true",
        "grep -c 'btn-add-aws' /opt/dlq-judge/dlq_judge/ui/index.html || true",
        "grep -c aws_connector /opt/dlq-judge/dlq_judge/ui_server.py || true",
        "curl -sS http://127.0.0.1:8765/api/public/stats | head -c 400",
    ]
    resp = ssm.send_command(
        InstanceIds=[INSTANCE],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": cmds},
    )
    cid = resp["Command"]["CommandId"]
    print("ssm", cid)
    for _ in range(36):
        time.sleep(5)
        inv = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
        status = inv["Status"]
        print("status", status)
        if status in ("Success", "Failed", "Cancelled", "TimedOut"):
            print("stdout", (inv.get("StandardOutputContent") or "")[:1000])
            print("stderr", (inv.get("StandardErrorContent") or "")[:500])
            if status != "Success":
                sys.exit(1)
            break
    else:
        sys.exit("timeout")

    # Fix CloudFront origin if DNS changed
    if dns:
        cf = sess.client("cloudfront")
        dist_id = "<CLOUDFRONT_DISTRIBUTION_ID>"
        cfg = cf.get_distribution_config(Id=dist_id)
        conf = cfg["DistributionConfig"]
        etag = cfg["ETag"]
        origins = conf["Origins"]["Items"]
        cur = origins[0]["DomainName"]
        if cur != dns:
            print("cf origin", cur, "->", dns)
            origins[0]["DomainName"] = dns
            cf.update_distribution(Id=dist_id, IfMatch=etag, DistributionConfig=conf)
            print("cf updated")
        else:
            print("cf origin ok", cur)

    time.sleep(4)
    html = urllib.request.urlopen(
        "https://<CLOUDFRONT_DOMAIN>/", timeout=45
    ).read().decode("utf-8", "replace")
    for name, ok in [
        ("site-landing", 'id="site-landing"' in html),
        ("login-only", "login-only" in html),
        ("auth-gate", 'id="auth-gate"' in html),
        ("add-aws-btn", "btn-add-aws" in html),
        ("connect-panel", "aws-connect-panel" in html),
        ("not Connected badge", "Connected AWS account" not in html),
    ]:
        print(("PASS" if ok else "FAIL"), name)
    try:
        stats = urllib.request.urlopen(
            "https://<CLOUDFRONT_DOMAIN>/api/public/stats", timeout=45
        ).read().decode("utf-8", "replace")
        print("public_stats", stats[:300])
        print(("PASS" if '"has_run"' in stats else "FAIL"), "public_stats")
    except Exception as e:
        print("FAIL public_stats", e)
    print("DONE")


if __name__ == "__main__":
    main()
