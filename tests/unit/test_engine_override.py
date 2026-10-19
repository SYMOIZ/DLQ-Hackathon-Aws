"""TC-U22, U24, U32, U34–U36 (engine override / apply stubs)"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dlq_judge.config import Config
from dlq_judge import engine, runlog
from dlq_judge.models import RunMode, Status


def _cfg(tmp: Path) -> Config:
    return Config(
        aws_profile="dlqj",
        region="us-east-1",
        stack_name="dlq-judge",
        queue_prefix="dlqj-",
        source_queue="dlqj-orders",
        dlq="dlqj-orders-dlq",
        bucket="b",
        bedrock_model_id="amazon.nova-micro-v1:0",
        bedrock_max_calls=50,
        max_clusters=5,
        decider_url="http://127.0.0.1:8000",
        decider_model="x",
        decider_timeout_s=5,
        auto_min=0.85,
        review_min=0.60,
        discard_min=0.90,
        batch_size=300,
        redrive_delay_s=300,
        runs_dir=tmp,
        ui_port=8765,
        cognito_user_pool_id=None,
        cognito_client_id=None,
    )


def _seed_run(cfg: Config, run_id: str = "20261018T120000Z") -> Path:
    d = cfg.runs_dir / run_id
    d.mkdir(parents=True)
    rec = {
        "schema_version": 1,
        "run_id": run_id,
        "message_id": "mid-1",
        "fixture_id": None,
        "received_index": 0,
        "state": {
            "message_id": "mid-1",
            "source_queue": "dlqj-orders",
            "receive_count": 1,
            "age_minutes": 1,
            "error_type": "E",
            "error_text": "t",
            "has_idempotency_key": False,
            "body_masked": "{}",
        },
        "choice": "redrive_now",
        "confidence": 0.9,
        "probabilities": {},
        "band": "auto",
        "decider_ms": 1,
        "bedrock": None,
        "decided_by": "decider",
        "reason": "auto",
        "action": "redrive_now",
        "override": None,
        "status": "planned",
        "status_detail": None,
        "applied_at": None,
        "raw_body": "{}",
        "raw_attributes": {},
    }
    (d / "decisions.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    summary = runlog.build_summary(
        run_id=run_id,
        queue="dlqj-orders-dlq",
        source_queue="dlqj-orders",
        mode=RunMode.DRY_RUN,
        started_at="t0",
        finished_at="t1",
        records=[rec],
        cfg=cfg,
    )
    (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return d


def test_u32_override(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_run(cfg)
    updated = engine.override_message(cfg, "20261018T120000Z", "mid-1", action="quarantine_poison")
    assert updated["action"] == "quarantine_poison"
    assert updated["override"]["previous_action"] == "redrive_now"


def test_u34_revert(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_run(cfg)
    engine.override_message(cfg, "20261018T120000Z", "mid-1", action="quarantine_poison")
    updated = engine.override_message(cfg, "20261018T120000Z", "mid-1", action=None, revert=True)
    assert updated["action"] == "redrive_now"
    assert updated["override"] is None


def test_apply_requires_yes(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_run(cfg)
    with pytest.raises(SystemExit):
        engine.apply_run(cfg, "20261018T120000Z", yes=False)


def test_apply_not_found(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_run(cfg)
    with patch("dlq_judge.aws_io.receive_batch", return_value=[]), patch(
        "dlq_judge.aws_io.change_visibility"
    ):
        result = engine.apply_run(cfg, "20261018T120000Z", yes=True)
    assert result["skipped"] == 1
    decisions = runlog.load_decisions(tmp_path / "20261018T120000Z" / "decisions.jsonl")
    assert decisions[0]["status"] == Status.SKIPPED.value
