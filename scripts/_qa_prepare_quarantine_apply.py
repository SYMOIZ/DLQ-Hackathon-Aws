"""SSM: reset 3 decisions to planned quarantine_poison for S3 apply demo."""
from __future__ import annotations

import time
from pathlib import Path

import boto3

INSTANCE = "<EC2_INSTANCE_ID>"
REGION = "us-east-1"
OUT = Path("scripts/_qa_prepare_q_out.txt")

# Embed remote python as a single shell command
REMOTE = r'''
python3 <<'PY'
import json
from pathlib import Path
r = Path("/opt/dlq-judge/runs/20261018T160623Z")
dec_path = r / "decisions.jsonl"
lines = dec_path.read_text().strip().splitlines()
docs = [json.loads(x) for x in lines]
n = 0
for d in docs:
    if n >= 3:
        break
    if d.get("status") == "applied" and d.get("action") == "escalate_human":
        d["action"] = "quarantine_poison"
        d["status"] = "planned"
        d["status_detail"] = None
        d["applied_at"] = None
        d["override"] = {
            "action": "quarantine_poison",
            "previous_action": "escalate_human",
            "at": "2026-10-18T16:35:00Z",
            "reason": "qa_s3_demo",
        }
        n += 1
summary = json.loads((r / "summary.json").read_text())
summary["mode"] = "dry_run"
from collections import Counter
acts = Counter(d.get("action") for d in docs)
sts = Counter(d.get("status") for d in docs)
summary["counts"] = {k: acts.get(k, 0) for k in (
    "redrive_now","redrive_later","quarantine_poison","discard_duplicate","escalate_human")}
summary["status_counts"] = {k: sts.get(k, 0) for k in ("planned","applied","skipped","failed")}
summary["actionable_count"] = sts.get("planned", 0) + sts.get("failed", 0)
dec_path.write_text("\n".join(json.dumps(d) for d in docs) + "\n")
(r / "summary.json").write_text(json.dumps(summary, indent=2))
print("rewrote", n, "to quarantine planned; actionable", summary["actionable_count"])
print("actions", dict(acts))
print("statuses", dict(sts))
PY
'''

session = boto3.Session(profile_name="default", region_name=REGION)
ssm = session.client("ssm")
resp = ssm.send_command(
    InstanceIds=[INSTANCE],
    DocumentName="AWS-RunShellScript",
    Parameters={"commands": [REMOTE]},
    TimeoutSeconds=120,
)
cid = resp["Command"]["CommandId"]
print(f"command_id={cid}", flush=True)
for _ in range(40):
    time.sleep(3)
    try:
        inv = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    except Exception:
        continue
    if inv["Status"] in ("Success", "Failed", "TimedOut", "Cancelled"):
        text = (inv.get("StandardOutputContent") or "") + "\n" + (
            inv.get("StandardErrorContent") or ""
        )
        OUT.write_text(text, encoding="utf-8", errors="replace")
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)
        raise SystemExit(0 if inv["Status"] == "Success" else 1)
raise SystemExit("timeout")
