"""TC-U07–U14, U32-ish"""

from dlq_judge.models import Action, Band, DeciderResult, Reason, State
from dlq_judge.policy import apply_bedrock, decide


def _state(**kw):
    base = dict(
        message_id="m",
        source_queue="dlqj-orders",
        receive_count=1,
        age_minutes=1,
        error_type="TimeoutError",
        error_text="t",
        has_idempotency_key=False,
        body_masked="{}",
    )
    base.update(kw)
    return State(**base)


def _res(choice="redrive_now", conf=0.85):
    probs = {a.value: 0.0 for a in Action}
    probs[choice] = conf
    return DeciderResult(choice=choice, probabilities=probs, confidence=conf, latency_ms=1)


def test_u07_auto():
    v = decide(_state(), _res("redrive_now", 0.85))
    assert v.band == Band.AUTO and v.reason == Reason.AUTO
    assert v.action == Action.REDRIVE_NOW


def test_u08_review_below_auto():
    v = decide(_state(), _res("redrive_now", 0.849))
    assert v.band == Band.REVIEW


def test_u09_review_at_min():
    v = decide(_state(), _res("redrive_now", 0.60))
    assert v.band == Band.REVIEW


def test_u10_low():
    v = decide(_state(), _res("redrive_now", 0.59))
    assert v.band == Band.LOW and v.action == Action.ESCALATE_HUMAN


def test_u11_missing_evidence():
    v = decide(_state(error_type=None, error_text=None), _res())
    assert v.reason == Reason.MISSING_EVIDENCE


def test_u12_discard_guard_no_key():
    v = decide(_state(has_idempotency_key=False), _res("discard_duplicate", 0.95))
    assert v.reason == Reason.DISCARD_GUARD


def test_u13_discard_ok():
    v = decide(_state(has_idempotency_key=True), _res("discard_duplicate", 0.95))
    assert v.action == Action.DISCARD_DUPLICATE


def test_u14_bedrock_cap_on_review():
    v = decide(_state(), _res("redrive_now", 0.7), bedrock_cap_reached=True)
    assert v.reason == Reason.BEDROCK_CAP


def test_bedrock_agree_disagree():
    v = decide(_state(), _res("redrive_now", 0.7))
    ok = apply_bedrock(v, "redrive_now", valid=True)
    assert ok.reason == Reason.BEDROCK_AGREE
    bad = apply_bedrock(v, "escalate_human", valid=True)
    assert bad.reason == Reason.BEDROCK_DISAGREE
    inv = apply_bedrock(v, None, valid=False)
    assert inv.reason == Reason.BEDROCK_INVALID
