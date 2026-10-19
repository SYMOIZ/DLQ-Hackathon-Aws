"""Seed dataset into DLQ."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dlq_judge import aws_io
from dlq_judge.config import get_config


def main() -> int:
    cfg = get_config(reload=True)
    path = Path("bench/dataset/messages.jsonl")
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    force = "--force" in sys.argv
    depth = aws_io.approx_depth(cfg, cfg.dlq)
    print(f"depth_before={depth}", flush=True)
    if depth > 0 and not force:
        print("refused: not empty; pass --force", flush=True)
        return 1
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()][:count]
    for i, ln in enumerate(lines, 1):
        obj = json.loads(ln)
        body = obj["body"] if isinstance(obj["body"], str) else json.dumps(obj["body"])
        attrs = dict(obj.get("attributes") or {})
        if "fixture_id" not in attrs and obj.get("fixture_id"):
            attrs["fixture_id"] = obj["fixture_id"]
        aws_io.send_message(cfg, cfg.dlq, body, attrs)
        if i % 25 == 0 or i == len(lines):
            print(f"seeded {i}/{len(lines)}", flush=True)
    print(f"depth_after={aws_io.approx_depth(cfg, cfg.dlq)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
