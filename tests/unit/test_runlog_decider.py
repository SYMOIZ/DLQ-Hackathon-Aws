"""TC-U15, U25, U28, U29, U33"""

from datetime import datetime, timezone
from pathlib import Path

from dlq_judge.config import Config
from dlq_judge.decider_client import confidence_from_pmax
from dlq_judge.models import Action, DecisionRecord, RunMode, State, Status
from dlq_judge import runlog
from patterns.failed_message_recovery.question import OPTIONS, QUESTION, render_state


def test_u28_confidence_formula():
    assert abs(confidence_from_pmax(1.0) - 1.0) < 1e-9
    assert abs(confidence_from_pmax(0.2) - 0.0) < 1e-9


def test_u33_question_options():
    assert len(OPTIONS) == 5
    assert "redrive_now" in OPTIONS
    st = State(
        message_id="m",
        source_queue="q",
        receive_count=1,
        age_minutes=1,
        error_type="E",
        error_text="t",
        has_idempotency_key=False,
        body_masked="{}",
    )
    text = render_state(st)
    assert "error_type=E" in text
    assert QUESTION


def test_u25_u29_runlog(tmp_path: Path):
    cfg = Config(
        aws_profile="dlqj",
        region="us-east-1",
        stack_name="dlq-judge",
        queue_prefix="dlqj-",
        source_queue="dlqj-orders",
        dlq="dlqj-orders-dlq",
        bucket=None,
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
        runs_dir=tmp_path,
        ui_port=8765,
        cognito_user_pool_id=None,
        cognito_client_id=None,
    )
    rid = runlog.new_run_id(datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc))
    assert rid == "20261018T120000Z"
    hist = runlog.confidence_histogram([0.29, 0.30, 0.325, 1.0, None])
    assert len(hist) == 28
    assert hist[0] >= 1
    rec = DecisionRecord(
        schema_version=1,
        run_id=rid,
        message_id="m1",
        fixture_id=None,
        received_index=0,
        state=State(
            "m1", "dlqj-orders", 1, 1, "E", "t", False, "{}"
        ),
        choice="redrive_now",
        confidence=0.9,
        probabilities={a.value: 0.2 for a in Action},
        band="auto",
        decider_ms=10,
        bedrock=None,
        decided_by="decider",
        reason="auto",
        action="redrive_now",
        override=None,
        status=Status.PLANNED.value,
        status_detail=None,
        applied_at=None,
    )
    d = runlog.run_dir(cfg, rid)
    runlog.write_decisions(d / "decisions.jsonl", [rec])
    loaded = runlog.load_decisions(d / "decisions.jsonl")
    assert loaded[0]["message_id"] == "m1"
    summary = runlog.build_summary(
        run_id=rid,
        queue="dlqj-orders-dlq",
        source_queue="dlqj-orders",
        mode=RunMode.DRY_RUN,
        started_at="t0",
        finished_at="t1",
        records=loaded,
        cfg=cfg,
    )
    assert summary["processed"] == 1
    assert len(summary["confidence_histogram"]) == 28
