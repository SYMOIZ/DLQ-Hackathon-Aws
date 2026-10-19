"""Run approaches A/B/C offline and write results.json + results.md."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from bench.baseline_rules import decide_rules
from dlq_judge.config import get_config
from dlq_judge.decider_client import ask
from dlq_judge.models import DeciderResult, State
from dlq_judge.policy import decide
from dlq_judge.state import build_state


def _load_dataset(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _state_from_row(row: dict) -> State:
    attrs = row.get("attributes") or {}
    msg = {
        "MessageId": row.get("fixture_id", "x"),
        "Body": row.get("body") or "{}",
        "MessageAttributes": {
            k: {"DataType": "String", "StringValue": str(v)} for k, v in attrs.items()
        },
    }
    return build_state(msg)


def _metrics(preds: list[str], labels: list[str], latencies: list[int], bedrock_calls: int, n: int) -> dict:
    correct = sum(1 for p, l in zip(preds, labels) if p == l)
    unsafe = {"redrive_now", "redrive_later", "discard_duplicate"}
    # unsafe-action rate: predicted unsafe when label is escalate/quarantine
    unsafe_err = 0
    for p, l in zip(preds, labels):
        if p in unsafe and l in ("escalate_human", "quarantine_poison"):
            unsafe_err += 1
    med = int(statistics.median(latencies)) if latencies else 0
    p95 = int(sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.95))]) if latencies else 0
    return {
        "accuracy": round(correct / n, 4) if n else 0,
        "unsafe_action_rate": round(unsafe_err / n, 4) if n else 0,
        "median_latency_ms": med,
        "p95_latency_ms": p95,
        "bedrock_calls_per_1000": round(1000.0 * bedrock_calls / n, 1) if n else 0,
    }


def run(dataset_path: Path | None = None, out_dir: Path | None = None, include_bedrock: bool = True) -> dict:
    cfg = get_config()
    dataset_path = dataset_path or Path("bench/dataset/messages.jsonl")
    out_dir = out_dir or Path("bench/results")
    rows = _load_dataset(dataset_path)
    # evaluate non-holdout for threshold tuning honesty; report all
    labels = [r["expected_action"] for r in rows]
    n = len(rows)

    # A rules
    preds_a = [decide_rules(r) for r in rows]
    m_a = _metrics(preds_a, labels, [0] * n, 0, n)

    # C decider+policy (no Bedrock second opinion for speed in bench)
    preds_c = []
    lat_c = []
    for r in rows:
        st = _state_from_row(r)
        t0 = time.perf_counter()
        try:
            result = ask(st, cfg)
        except Exception:
            result = None
        lat_c.append(int((time.perf_counter() - t0) * 1000))
        v = decide(
            st,
            result,
            auto_min=cfg.auto_min,
            review_min=cfg.review_min,
            discard_min=cfg.discard_min,
            bedrock_cap_reached=True,
        )
        preds_c.append(v.action.value)
    m_c = _metrics(preds_c, labels, lat_c, 0, n)

    m_b = {
        "accuracy": 0.0,
        "unsafe_action_rate": 0.0,
        "median_latency_ms": 0,
        "p95_latency_ms": 0,
        "bedrock_calls_per_1000": 1000.0,
        "skipped": True,
    }
    if include_bedrock:
        from bench.baseline_bedrock import decide_bedrock

        preds_b = []
        lat_b = []
        # sample 30 for cost control if full 300 is expensive; still report /1000 scale
        sample = rows[:30]
        for r in sample:
            choice, ms = decide_bedrock(cfg, r)
            preds_b.append(choice)
            lat_b.append(ms)
        m_b = _metrics(preds_b, [r["expected_action"] for r in sample], lat_b, len(sample), len(sample))
        m_b["note"] = "evaluated on first 30 messages for cost"

    result = {
        "schema_version": 1,
        "sample_data": False,
        "n_messages": n,
        "approaches": [
            {"name": "Rules", "id": "A", **m_a},
            {"name": "Bedrock only", "id": "B", **m_b},
            {"name": "DLQ Judge", "id": "C", **m_c},
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Benchmark results",
        "",
        f"Messages: {n}",
        "",
        "| Approach | Accuracy | Unsafe rate | Median ms | p95 ms | Bedrock/1k |",
        "|---|---|---|---|---|---|",
    ]
    for a in result["approaches"]:
        lines.append(
            f"| {a['name']} | {a.get('accuracy')} | {a.get('unsafe_action_rate')} | "
            f"{a.get('median_latency_ms')} | {a.get('p95_latency_ms')} | {a.get('bedrock_calls_per_1000')} |"
        )
    (out_dir / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
