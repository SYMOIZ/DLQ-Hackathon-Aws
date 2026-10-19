"""Layer 4: triage, apply, override/revert, restore orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dlq_judge import actions, aws_io, bedrock_client, clusters, decider_client, runlog
from dlq_judge.config import Config
from dlq_judge.models import (
    Action,
    Band,
    BedrockOpinion,
    DecidedBy,
    DecisionRecord,
    OverrideInfo,
    Reason,
    RunMode,
    Status,
    to_jsonable,
)
from dlq_judge.policy import apply_bedrock, decide
from dlq_judge.state import build_state


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _attrs_plain(msg: dict) -> dict[str, Any]:
    raw = msg.get("MessageAttributes") or {}
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[k] = v.get("StringValue") or v.get("Value") or ""
        else:
            out[k] = v
    return out


def triage(cfg: Config, *, apply: bool = False) -> str:
    run_id = runlog.new_run_id()
    rdir = runlog.run_dir(cfg, run_id)
    started = _now()
    records: list[DecisionRecord] = []
    bedrock_second = 0
    messages: list[dict] = []
    remaining = cfg.batch_size
    empty_streak = 0
    while remaining > 0 and empty_streak < 5:
        batch = aws_io.receive_batch(cfg, cfg.dlq, max_messages=min(10, remaining))
        if not batch:
            empty_streak += 1
            continue
        empty_streak = 0
        messages.extend(batch)
        remaining -= len(batch)

    for idx, msg in enumerate(messages):
        state = build_state(msg)
        fixture_id = None
        attrs = msg.get("MessageAttributes") or {}
        if "fixture_id" in attrs:
            fixture_id = attrs["fixture_id"].get("StringValue")
        result = None
        reason = Reason.MISSING_EVIDENCE
        band = Band.NONE
        decided_by = DecidedBy.RULE
        action = Action.ESCALATE_HUMAN
        bedrock_op = None
        if state.error_type is not None or state.error_text is not None:
            try:
                result = decider_client.ask(state, cfg)
            except Exception:
                result = None
                reason = Reason.DECIDER_UNAVAILABLE
            verdict = decide(
                state,
                result,
                auto_min=cfg.auto_min,
                review_min=cfg.review_min,
                discard_min=cfg.discard_min,
                bedrock_cap_reached=bedrock_second >= cfg.bedrock_max_calls,
            )
            action, band, reason, decided_by = (
                verdict.action,
                verdict.band,
                verdict.reason,
                verdict.decided_by,
            )
            if (
                verdict.band == Band.REVIEW
                and verdict.reason != Reason.BEDROCK_CAP
                and verdict.reason != Reason.DISCARD_GUARD
            ):
                if bedrock_second < cfg.bedrock_max_calls:
                    try:
                        br = bedrock_client.second_opinion(cfg, state, result.choice if result else action.value)
                        bedrock_second += 1
                        bedrock_op = BedrockOpinion(
                            choice=br["choice"],
                            reason=br["reason"],
                            agrees=br["choice"] == (result.choice if result else ""),
                            latency_ms=br["latency_ms"],
                        )
                        verdict = apply_bedrock(
                            verdict, br["choice"], valid=br.get("valid", True)
                        )
                        action, band, reason, decided_by = (
                            verdict.action,
                            verdict.band,
                            verdict.reason,
                            verdict.decided_by,
                        )
                        bedrock_op.agrees = reason == Reason.BEDROCK_AGREE
                    except Exception:
                        verdict = apply_bedrock(verdict, None, valid=False)
                        action, band, reason, decided_by = (
                            verdict.action,
                            verdict.band,
                            verdict.reason,
                            verdict.decided_by,
                        )
                else:
                    action, reason, decided_by = (
                        Action.ESCALATE_HUMAN,
                        Reason.BEDROCK_CAP,
                        DecidedBy.RULE,
                    )

        rec = DecisionRecord(
            schema_version=1,
            run_id=run_id,
            message_id=state.message_id,
            fixture_id=fixture_id,
            received_index=idx,
            state=state,
            choice=result.choice if result else None,
            confidence=result.confidence if result else None,
            probabilities=result.probabilities if result else None,
            band=band.value if band else None,
            decider_ms=result.latency_ms if result else None,
            bedrock=bedrock_op,
            decided_by=decided_by.value,
            reason=reason.value,
            action=action.value,
            override=None,
            status=Status.PLANNED.value,
            status_detail=None,
            applied_at=None,
            receipt_handle=msg.get("ReceiptHandle"),
            raw_body=msg.get("Body") or "",
            raw_attributes=_attrs_plain(msg),
        )
        records.append(rec)

    # Dry run: no Send/Delete/ChangeVisibility — messages reappear after visibility timeout.

    dicts = [to_jsonable(r) for r in records]
    cluster_calls = 0
    cluster_data = clusters.build_and_explain(cfg, dicts)
    cluster_calls = cluster_data.get("bedrock_calls", 0)
    runlog.atomic_write(
        rdir / "clusters.json", json.dumps(cluster_data, indent=2)
    )
    finished = _now()
    summary = runlog.build_summary(
        run_id=run_id,
        queue=cfg.dlq,
        source_queue=cfg.source_queue,
        mode=RunMode.DRY_RUN,
        started_at=started,
        finished_at=finished,
        records=dicts,
        cfg=cfg,
        bedrock_second=bedrock_second,
        bedrock_cluster=cluster_calls,
        quarantine_uri=f"s3://{cfg.bucket}/" if cfg.bucket else None,
    )
    runlog.atomic_write(rdir / "summary.json", json.dumps(summary, indent=2))
    runlog.write_decisions(rdir / "decisions.jsonl", records)

    if apply:
        apply_run(cfg, run_id, yes=True)
    return run_id


def apply_run(cfg: Config, run_id: str, *, yes: bool = False) -> dict[str, int]:
    if not yes:
        raise SystemExit("apply requires --yes")
    rdir = cfg.runs_dir / run_id
    decisions = runlog.load_decisions(rdir / "decisions.jsonl")
    targets = {
        d["message_id"]: d
        for d in decisions
        if d.get("status") in (Status.PLANNED.value, Status.FAILED.value)
        and d.get("action") != Action.ESCALATE_HUMAN.value
    }
    # also apply escalate (visibility 0) 
    escalate_targets = {
        d["message_id"]: d
        for d in decisions
        if d.get("status") in (Status.PLANNED.value, Status.FAILED.value)
        and d.get("action") == Action.ESCALATE_HUMAN.value
    }
    all_targets = {**targets, **escalate_targets}
    applied = skipped = failed = 0
    seen: set[str] = set()
    empty_rounds = 0
    # Cap scan effort so a polluted DLQ cannot loop forever looking for targets.
    max_rounds = max(30, len(all_targets) * 5)
    rounds = 0
    while len(seen) < len(all_targets) and empty_rounds < 3 and rounds < max_rounds:
        rounds += 1
        batch = aws_io.receive_batch(cfg, cfg.dlq, max_messages=10, visibility=300)
        if not batch:
            empty_rounds += 1
            continue
        empty_rounds = 0
        matched_any = False
        for msg in batch:
            mid = msg["MessageId"]
            if mid not in all_targets or mid in seen:
                aws_io.change_visibility(cfg, cfg.dlq, msg["ReceiptHandle"], 0)
                continue
            matched_any = True
            d = all_targets[mid]
            seen.add(mid)
            try:
                actions.execute(
                    cfg,
                    action=d["action"],
                    run_id=run_id,
                    message_id=mid,
                    receipt_handle=msg["ReceiptHandle"],
                    body=msg.get("Body") or d.get("raw_body") or "",
                    attributes=d.get("raw_attributes") or {},
                    decision=d,
                )
                d["status"] = Status.APPLIED.value
                d["applied_at"] = _now()
                d["status_detail"] = None
                applied += 1
            except Exception as e:
                d["status"] = Status.FAILED.value
                d["status_detail"] = str(e)
                failed += 1
        if not matched_any:
            empty_rounds += 1
    for mid, d in all_targets.items():
        if mid not in seen and d.get("status") in (
            Status.PLANNED.value,
            Status.FAILED.value,
        ):
            d["status"] = Status.SKIPPED.value
            d["status_detail"] = "not_found"
            skipped += 1

    # write back
    from dlq_judge.models import DecisionRecord as DR  # noqa — use dicts

    class _Wrap:
        pass

    # decisions are dicts; write JSONL directly
    lines = [json.dumps(d) for d in decisions]
    runlog.atomic_write(rdir / "decisions.jsonl", "\n".join(lines) + "\n")
    summary = json.loads((rdir / "summary.json").read_text(encoding="utf-8"))
    if all(
        d.get("status") in (Status.APPLIED.value, Status.SKIPPED.value)
        for d in decisions
        if d.get("status") != Status.FAILED.value
    ):
        # mode becomes applied when no planned/failed remain among actionable
        still = [
            d
            for d in decisions
            if d.get("status") in (Status.PLANNED.value, Status.FAILED.value)
        ]
        if not still:
            summary["mode"] = RunMode.APPLIED.value
    summary["status_counts"] = {}
    for s in Status:
        summary["status_counts"][s.value] = sum(
            1 for d in decisions if d.get("status") == s.value
        )
    summary["actionable_count"] = sum(
        1
        for d in decisions
        if d.get("status") in (Status.PLANNED.value, Status.FAILED.value)
    )
    runlog.atomic_write(rdir / "summary.json", json.dumps(summary, indent=2))
    return {"applied": applied, "skipped": skipped, "failed": failed}


def override_message(
    cfg: Config, run_id: str, message_id: str, *, action: str | None, revert: bool = False
) -> dict[str, Any]:
    rdir = cfg.runs_dir / run_id
    summary = json.loads((rdir / "summary.json").read_text(encoding="utf-8"))
    if summary.get("mode") == RunMode.APPLIED.value:
        raise RuntimeError("conflict: run already applied")
    decisions = runlog.load_decisions(rdir / "decisions.jsonl")
    found = None
    for d in decisions:
        if d["message_id"] == message_id:
            found = d
            break
    if not found:
        raise KeyError("not_found")
    if found.get("status") not in (Status.PLANNED.value, Status.FAILED.value):
        raise RuntimeError("conflict: status not planned/failed")
    if revert:
        if not found.get("override"):
            raise RuntimeError("conflict: no override to revert")
        prev = found["override"]["previous_action"]
        found["action"] = prev
        found["override"] = None
    else:
        if action not in {a.value for a in Action}:
            raise ValueError("bad_request")
        prev = found["action"]
        found["override"] = {
            "action": action,
            "previous_action": prev,
            "at": _now(),
            "reason": "human",
        }
        found["action"] = action
    lines = [json.dumps(d) for d in decisions]
    runlog.atomic_write(rdir / "decisions.jsonl", "\n".join(lines) + "\n")
    # recompute counts
    summary = runlog.build_summary(
        run_id=run_id,
        queue=summary["queue"],
        source_queue=summary["source_queue"],
        mode=RunMode(summary["mode"]),
        started_at=summary["started_at"],
        finished_at=summary["finished_at"],
        records=decisions,
        cfg=cfg,
        bedrock_second=summary.get("bedrock_second_opinion_calls", 0),
        bedrock_cluster=summary.get("bedrock_cluster_calls", 0),
        quarantine_uri=summary.get("quarantine_uri"),
        versions=summary.get("versions"),
    )
    runlog.atomic_write(rdir / "summary.json", json.dumps(summary, indent=2))
    return found


def restore(cfg: Config, run_id: str, message_id: str | None = None, *, apply: bool = False, yes: bool = False) -> int:
    if apply and not yes:
        raise SystemExit("restore --apply requires --yes")
    prefix = f"backup/{run_id}/"
    # list via get for known decisions
    decisions = runlog.load_decisions(cfg.runs_dir / run_id / "decisions.jsonl")
    ids = [message_id] if message_id else [d["message_id"] for d in decisions]
    n = 0
    for mid in ids:
        key = f"{prefix}{mid}.json"
        try:
            obj = aws_io.s3_get_json(cfg, key)
        except Exception:
            continue
        if not apply:
            n += 1
            continue
        aws_io.send_message(cfg, cfg.dlq, obj["body"], obj.get("attributes"))
        n += 1
    return n
