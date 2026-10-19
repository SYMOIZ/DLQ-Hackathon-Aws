"""Inspect apply result + decision statuses on instance."""
from __future__ import annotations

import time
from pathlib import Path

import boto3

INSTANCE = "<EC2_INSTANCE_ID>"
REGION = "us-east-1"
OUT = Path("scripts/_qa_apply_inspect.txt")

COMMANDS = [
    "python3 - <<'PY'\n"
    "import json, pathlib\n"
    "r=pathlib.Path('/opt/dlq-judge/runs/20261018T160623Z')\n"
    "s=json.loads((r/'summary.json').read_text())\n"
    "print('summary', json.dumps({k:s.get(k) for k in ('run_id','queue','mode','processed','counts','status_counts','actionable_count')}, indent=2))\n"
    "lines=(r/'decisions.jsonl').read_text().strip().splitlines()\n"
    "from collections import Counter\n"
    "acts=Counter(); sts=Counter()\n"
    "for ln in lines:\n"
    " d=json.loads(ln); acts[d.get('action')]+=1; sts[d.get('status')]+=1\n"
    "print('actions', dict(acts))\n"
    "print('statuses', dict(sts))\n"
    "print('sample mid', json.loads(lines[0]).get('message_id'))\n"
    "PY",
    "ls /opt/dlq-judge/runs/_jobs | tail -5",
    "python3 - <<'PY'\n"
    "import json, pathlib\n"
    "p=pathlib.Path('/opt/dlq-judge/runs/_jobs')\n"
    "for f in sorted(p.glob('*.json'))[-5:]:\n"
    " print(f.name, f.read_text()[:400])\n"
    "PY",
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
    except Exception:
        continue
    if inv["Status"] in ("Success", "Failed", "TimedOut", "Cancelled"):
        text = (inv.get("StandardOutputContent") or "") + "\nERR\n" + (
            inv.get("StandardErrorContent") or ""
        )
        OUT.write_text(text, encoding="utf-8", errors="replace")
        print(text.encode("ascii", "replace").decode("ascii")[:4000], flush=True)
        raise SystemExit(0 if inv["Status"] == "Success" else 1)
raise SystemExit("timeout")
