"""Package, upload to S3, SSM install/restart UI."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "<EC2_INSTANCE_ID>"
REGION = "us-east-1"
BUCKET = "dlqj-deploy-<AWS_ACCOUNT_ID>"
OUT = Path("scripts/_qa_redeploy_out.txt")

print("packaging...", flush=True)
subprocess.check_call(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "package_app.ps1")],
    cwd=str(ROOT),
)
tgz = ROOT / "dist" / "dlq-judge-app.tgz"
print(f"upload {tgz} ({tgz.stat().st_size} bytes)", flush=True)
session = boto3.Session(profile_name="default", region_name=REGION)
s3 = session.client("s3")
s3.upload_file(str(tgz), BUCKET, "app/dlq-judge-app.tgz")

commands = [
    "aws s3 cp s3://dlqj-deploy-<AWS_ACCOUNT_ID>/app/dlq-judge-app.tgz /tmp/dlq-judge-app.tgz --region us-east-1",
    "tar -xzf /tmp/dlq-judge-app.tgz -C /opt/dlq-judge",
    "/opt/dlq-judge/.venv/bin/pip install -e /opt/dlq-judge -q",
    "systemctl restart dlqj-ui",
    "sleep 2",
    "systemctl is-active dlqj-ui",
    "curl -sS -m 5 http://127.0.0.1:8765/healthz",
]

ssm = session.client("ssm")
resp = ssm.send_command(
    InstanceIds=[INSTANCE],
    DocumentName="AWS-RunShellScript",
    Parameters={"commands": commands},
    TimeoutSeconds=300,
)
cid = resp["Command"]["CommandId"]
print(f"ssm command_id={cid}", flush=True)
for _ in range(80):
    time.sleep(3)
    try:
        inv = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    except Exception:
        continue
    if inv["Status"] in ("Success", "Failed", "TimedOut", "Cancelled"):
        text = (inv.get("StandardOutputContent") or "") + "\nERR\n" + (
            inv.get("StandardErrorContent") or ""
        )
        OUT.write_text(text, encoding="utf-8", errors="replace")
        print(text.encode("ascii", "replace").decode("ascii")[:3000], flush=True)
        raise SystemExit(0 if inv["Status"] == "Success" else 1)
raise SystemExit("timeout")
