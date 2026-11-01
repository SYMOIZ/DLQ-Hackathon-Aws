"""Bedrock-backed Decider (DLQJ_DECIDER_URL=bedrock)."""

from types import SimpleNamespace

from dlq_judge import bedrock_client, decider_client
from dlq_judge.models import State

ST = State(
    message_id="m",
    source_queue="q",
    receive_count=1,
    age_minutes=1,
    error_type="TimeoutError",
    error_text="timed out",
    has_idempotency_key=False,
    body_masked="{}",
)
CFG = SimpleNamespace(decider_url="bedrock", decider_model="StrandsAgents/x", bedrock_model_id="amazon.nova-micro-v1:0")


def test_probabilities_are_normalised_and_unknown_options_dropped(monkeypatch):
    seen = {}

    def fake(cfg, system, user, *, model_id=None):
        seen["model"] = model_id
        return '{"probabilities": {"redrive_later": 3, "redrive_now": 1, "bogus": 5}}', 42

    monkeypatch.setattr(bedrock_client, "_converse", fake)
    r = decider_client.ask(ST, CFG)
    assert r.choice == "redrive_later"
    assert abs(r.probabilities["redrive_later"] - 0.75) < 1e-9
    assert r.probabilities["escalate_human"] == 0.0
    assert r.latency_ms == 42
    assert seen["model"] == "amazon.nova-micro-v1:0"  # non-Bedrock decider_model falls back


def test_no_json_raises(monkeypatch):
    monkeypatch.setattr(bedrock_client, "_converse", lambda *a, **k: ("sorry", 1))
    try:
        decider_client.ask(ST, CFG)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
