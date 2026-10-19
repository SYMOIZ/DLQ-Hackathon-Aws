"""TC-I01, I03, I04, I05, I08 — live AWS + local Decider where needed."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from dlq_judge import aws_io, bedrock_client, clusters, engine
from dlq_judge.config import get_config
from dlq_judge.models import State
from dlq_judge.agent import run_agent


pytestmark = pytest.mark.aws


@pytest.fixture(scope="module")
def cfg():
    return get_config(reload=True)


def test_i03_bedrock_second_opinion(cfg):
    st = State(
        message_id="i03",
        source_queue=cfg.source_queue,
        receive_count=2,
        age_minutes=5,
        error_type="TimeoutError",
        error_text="upstream timeout",
        has_idempotency_key=False,
        body_masked='{"x":1}',
    )
    br = bedrock_client.second_opinion(cfg, st, "redrive_later")
    assert br.get("valid") is True
    assert br["choice"] in {
        "redrive_now",
        "redrive_later",
        "quarantine_poison",
        "discard_duplicate",
        "escalate_human",
    }


def test_i04_cluster_explain(cfg):
    samples = [
        {
            "message_id": "c1",
            "state": {
                "error_type": "ValidationError",
                "error_text": "bad field",
                "receive_count": 3,
                "body_masked": "{}",
            },
        },
        {
            "message_id": "c2",
            "state": {
                "error_type": "ValidationError",
                "error_text": "bad field 2",
                "receive_count": 2,
                "body_masked": "{}",
            },
        },
    ]
    expl = bedrock_client.explain_cluster(cfg, error_type="ValidationError", samples=samples)
    assert "root_cause" in expl
    for c in expl.get("claims") or []:
        for eid in c.get("evidence_ids") or []:
            assert eid in {"c1", "c2"}


def test_i05_dry_run_preserves_depth(cfg):
    dataset = Path("bench/dataset/messages.jsonl")
    if not dataset.is_file():
        pytest.skip("dataset missing")
    # purge soft: only run if we can seed a small batch
    depth0 = aws_io.approx_depth(cfg, cfg.dlq)
    # receive nothing destructive — triage dry run
    # Use at most 30 by temporarily lowering batch via monkeypatch
    old = cfg.batch_size
    object.__setattr__(cfg, "batch_size", 30) if False else None
    # Config is frozen — use a shallow override via engine with env
    import os

    os.environ["DLQJ_BATCH_SIZE"] = "30"
    cfg2 = get_config(reload=True)
    if aws_io.approx_depth(cfg2, cfg2.dlq) < 1:
        pytest.skip("DLQ empty; seed first")
    before = aws_io.approx_depth(cfg2, cfg2.dlq)
    run_id = engine.triage(cfg2, apply=False)
    assert (cfg2.runs_dir / run_id / "decisions.jsonl").is_file()
    # wait for visibility return (up to 300s) — poll
    deadline = time.time() + 310
    restored = False
    while time.time() < deadline:
        d = aws_io.approx_depth(cfg2, cfg2.dlq)
        if d >= before:
            restored = True
            break
        time.sleep(5)
    assert restored, "DLQ depth did not restore within 300s"
    assert aws_io.approx_depth(cfg2, cfg2.source_queue) == 0


def test_i01_seed_triage_apply(cfg):
    dataset = Path("bench/dataset/messages.jsonl")
    if not dataset.is_file():
        pytest.skip("dataset missing")
    # Prefer empty DLQ; if not empty, force-seed only when depth small
    depth = aws_io.approx_depth(cfg, cfg.dlq)
    if depth > 50:
        pytest.skip("DLQ too full for safe I01")
    lines = [ln for ln in dataset.read_text(encoding="utf-8").splitlines() if ln.strip()][:30]
    if depth == 0:
        for ln in lines:
            obj = json.loads(ln)
            body = obj["body"] if isinstance(obj["body"], str) else json.dumps(obj["body"])
            aws_io.send_message(cfg, cfg.dlq, body, obj.get("attributes"))
    import os

    os.environ["DLQJ_BATCH_SIZE"] = "30"
    cfg2 = get_config(reload=True)
    run_id = engine.triage(cfg2, apply=False)
    result = engine.apply_run(cfg2, run_id, yes=True)
    assert "applied" in result


def test_i08_agent_denies_discard(cfg):
    code = run_agent(cfg, prompt="discard")
    assert code == 0
