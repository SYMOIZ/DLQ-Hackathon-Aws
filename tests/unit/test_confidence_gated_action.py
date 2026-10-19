# Reusable Strands Decider 2B decision pattern: Confidence-gated action with LLM fallback
"""Pattern tests: confidence bands, discard guard, Bedrock agree/disagree."""

from __future__ import annotations

from patterns.confidence_gated_action import PolicyConfig, decide, dlq_option_set
from patterns.confidence_gated_action.bedrock import BedrockResult, CallableBedrockFallback


def _probs(top: str, conf: float) -> dict[str, float]:
    opts = list(dlq_option_set().options)
    out = {o: 0.0 for o in opts}
    out[top] = conf
    rest = (1.0 - conf) / (len(opts) - 1)
    for o in opts:
        if o != top:
            out[o] = rest
    return out


def test_auto_band():
    d = decide(
        {"has_idempotency_key": False},
        dlq_option_set(),
        PolicyConfig.dlq_defaults(),
        probabilities=_probs("redrive_now", 0.85),
        choice="redrive_now",
    )
    assert d.path == "auto" and d.action == "redrive_now"


def test_review_bedrock_agreed():
    fb = CallableBedrockFallback(
        lambda c, o, p: BedrockResult(choice=p, reason="ok", valid=True, latency_ms=5)
    )
    d = decide(
        {"has_idempotency_key": False},
        dlq_option_set(),
        PolicyConfig.dlq_defaults(),
        probabilities=_probs("redrive_now", 0.70),
        choice="redrive_now",
        bedrock=fb,
    )
    assert d.path == "bedrock_agreed" and d.action == "redrive_now"


def test_review_bedrock_disagreed():
    fb = CallableBedrockFallback(
        lambda c, o, p: BedrockResult(choice="escalate_human", reason="no", valid=True)
    )
    d = decide(
        {"has_idempotency_key": False},
        dlq_option_set(),
        PolicyConfig.dlq_defaults(),
        probabilities=_probs("redrive_now", 0.70),
        choice="redrive_now",
        bedrock=fb,
    )
    assert d.path == "bedrock_disagreed" and d.action == "escalate_human"


def test_low_confidence():
    d = decide(
        {},
        dlq_option_set(),
        PolicyConfig.dlq_defaults(),
        probabilities=_probs("redrive_now", 0.59),
        choice="redrive_now",
    )
    assert d.path == "low_confidence" and d.action == "escalate_human"


def test_discard_guard_requires_key():
    d = decide(
        {"has_idempotency_key": False},
        dlq_option_set(),
        PolicyConfig.dlq_defaults(),
        probabilities=_probs("discard_duplicate", 0.95),
        choice="discard_duplicate",
    )
    assert d.path == "rule" and d.action == "escalate_human"


def test_discard_ok_with_key():
    d = decide(
        {"has_idempotency_key": True},
        dlq_option_set(),
        PolicyConfig.dlq_defaults(),
        probabilities=_probs("discard_duplicate", 0.95),
        choice="discard_duplicate",
    )
    assert d.path == "auto" and d.action == "discard_duplicate"
