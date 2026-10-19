"""SSM diagnose + restart dlqj-ui if needed."""
from __future__ import annotations

import time
from pathlib import Path

import boto3

INSTANCE = "<EC2_INSTANCE_ID>"
REGION = "us-east-1"
OUT = Path("scripts/_qa_ssm_diag_out.txt")

COMMANDS = [
    "systemctl is-active dlqj-ui || true",
    "systemctl is-active dlqj-decider || true",
    "systemctl status dlqj-ui --no-pager -l 2>&1 | head -40 || true",
    "curl -sS -m 5 http://127.0.0.1:8765/healthz || echo CURL_FAIL",
    "ss -lntp 2>/dev/null | grep 8765 || true",
    "journalctl -u dlqj-ui -n 50 --no-pager 2>&1 | tr -cd '\\11\\12\\15\\40-\\176' | tail -50 || true",
    "ls -la /opt/dlq-judge/runs/ 2>/dev/null | head -30 || true",
    "find /opt/dlq-judge/runs -name decisions.jsonl 2>/dev/null | head -10 || true",
    "wc -l /opt/dlq-judge/runs/*/decisions.jsonl 2>/dev/null | head -10 || true",
]

session = boto3.Session(profile_name="default", region_name=REGION)
ssm = session.client("ssm")

print("sending SSM diag...", flush=True)
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
    print(f"status={st}", flush=True)
    if st in ("Success", "Cancelled", "TimedOut", "Failed"):
        text = (inv.get("StandardOutputContent") or "") + "\n---STDERR---\n" + (
            inv.get("StandardErrorContent") or ""
        )
        OUT.write_text(text, encoding="utf-8", errors="replace")
        print(f"wrote {OUT} ({len(text)} bytes)", flush=True)
        # ascii-safe preview
        print(text.encode("ascii", "replace").decode("ascii")[:2000], flush=True)
        raise SystemExit(0 if st == "Success" else 1)

raise SystemExit("timeout waiting SSM")
