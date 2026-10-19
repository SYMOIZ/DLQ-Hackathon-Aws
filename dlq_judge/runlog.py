"""Layer 3: run files, atomic writes, idempotency, histogram."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dlq_judge.config import Config
from dlq_judge.models import Action, Band, DecisionRecord, RunMode, Status, to_jsonable


def new_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ")


def run_dir(cfg: Config, run_id: str) -> Path:
    d = cfg.runs_dir / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_decisions(path: Path, records: Iterable[DecisionRecord]) -> None:
    lines = []
    for r in records:
        d = to_jsonable(r)
        # drop runtime-only fields from persisted JSON if desired — keep for restore
        lines.append(json.dumps(d, ensure_ascii=False))
    atomic_write(path, "\n".join(lines) + ("\n" if lines else ""))


def load_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def confidence_histogram(confidences: list[float | None]) -> list[int]:
    bins = [0] * 28
    for c in confidences:
        if c is None:
            continue
        if c < 0.30:
            bins[0] += 1
            continue
        idx = int((c - 0.30) / 0.025 + 1e-9)
        if idx >= 28:
            idx = 27
        if c >= 1.0:
            idx = 27
        bins[idx] += 1
    return bins


def build_summary(
    *,
    run_id: str,
    queue: str,
    source_queue: str,
    mode: RunMode,
    started_at: str,
    finished_at: str,
    records: list[dict[str, Any]],
    cfg: Config,
    bedrock_second: int = 0,
    bedrock_cluster: int = 0,
    quarantine_uri: str | None = None,
    versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    counts = {a.value: 0 for a in Action}
    status_counts = {s.value: 0 for s in Status}
    scored = 0
    rule = 0
    band_counts = {"auto": 0, "review": 0, "low": 0, "none": 0}
    discard_held = 0
    latencies: list[int] = []
    confs: list[float | None] = []
    for r in records:
        action = r.get("action")
        if action in counts:
            counts[action] += 1
        st = r.get("status")
        if st in status_counts:
            status_counts[st] += 1
        conf = r.get("confidence")
        confs.append(conf)
        if conf is None:
            rule += 1
            band_counts["none"] += 1
        else:
            scored += 1
            band = r.get("band") or "none"
            if band in band_counts:
                band_counts[band] += 1
            elif conf >= cfg.auto_min:
                band_counts["auto"] += 1
            elif conf >= cfg.review_min:
                band_counts["review"] += 1
            else:
                band_counts["low"] += 1
        if action == Action.DISCARD_DUPLICATE.value and (
            conf is None or conf < cfg.discard_min
        ):
            if r.get("status") in (Status.PLANNED.value, Status.FAILED.value):
                discard_held += 1
        if r.get("decider_ms") is not None:
            latencies.append(int(r["decider_ms"]))
    processed = len(records)
    actionable = sum(
        1
        for r in records
        if r.get("status") in (Status.PLANNED.value, Status.FAILED.value)
    )
    median = p95 = 0
    if latencies:
        s = sorted(latencies)
        median = s[len(s) // 2]
        p95 = s[min(len(s) - 1, int(len(s) * 0.95))]
    return {
        "schema_version": 1,
        "run_id": run_id,
        "queue": queue,
        "source_queue": source_queue,
        "mode": mode.value,
        "started_at": started_at,
        "finished_at": finished_at,
        "processed": processed,
        "scored_count": scored,
        "rule_count": rule,
        "counts": counts,
        "status_counts": status_counts,
        "actionable_count": actionable,
        "median_decider_ms": median,
        "p95_decider_ms": p95,
        "bedrock_calls": bedrock_second + bedrock_cluster,
        "bedrock_second_opinion_calls": bedrock_second,
        "bedrock_cluster_calls": bedrock_cluster,
        "baseline_bedrock_calls": processed,
        "confidence_histogram": confidence_histogram(confs),
        "band_counts": band_counts,
        "discard_held_count": discard_held,
        "quarantine_uri": quarantine_uri,
        "thresholds": {
            "auto_min": cfg.auto_min,
            "review_min": cfg.review_min,
            "discard_min": cfg.discard_min,
            "bedrock_max_calls": cfg.bedrock_max_calls,
            "max_clusters": cfg.max_clusters,
        },
        "decider_model": cfg.decider_model,
        "bedrock_model_id": cfg.bedrock_model_id,
        "versions": versions or {"dlq_judge": "1.0.0"},
    }
