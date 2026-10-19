"""Restart dlqj-ui via SSM and verify local healthz."""
from __future__ import annotations

import time
from pathlib import Path

import boto3

INSTANCE = "<EC2_INSTANCE_ID>"
REGION = "us-east-1"
OUT = Path("scripts/_qa_ssm_restart_out.txt")

COMMANDS = [
    "systemctl restart dlqj-ui",
    "sleep 2",
    "systemctl is-active dlqj-ui",
    "curl -sS -m 5 http://127.0.0.1:8765/healthz || echo CURL_FAIL",
    "curl -sS -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/ || true",
    "echo",
    "cat /etc/dlqj.env | grep -E 'BIND|PORT|PUBLIC|ALLOW' || true",
]

session = boto3.Session(profile_name="default", region_name=REGION)
ssm = session.client("ssm")

resp = ssm.send_command(
    InstanceIds=[INSTANCE],
    DocumentName="AWS-RunShellScript",
    Parameters={"commands": COMMANDS},
    TimeoutSeconds=120,
)
cid = resp["Command"]["CommandId"]
print(f"command_id={cid}", flush=True)

for _ in range(40):
    time.sleep(3)
    try:
        inv = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    except ssm.exceptions.InvocationDoesNotExist:
        continue
    st = inv["Status"]
    if st in ("Success", "Cancelled", "TimedOut", "Failed"):
        text = (inv.get("StandardOutputContent") or "") + "\n---STDERR---\n" + (
            inv.get("StandardErrorContent") or ""
        )
        OUT.write_text(text, encoding="utf-8", errors="replace")
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)
        raise SystemExit(0 if st == "Success" else 1)

raise SystemExit("timeout")
