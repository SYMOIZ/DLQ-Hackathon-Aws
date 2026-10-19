"""Layer 1: confidence bands — uses confidence-gated-action pattern."""

from __future__ import annotations

from dataclasses import dataclass

from dlq_judge.models import (
    Action,
    Band,
    DecidedBy,
    DeciderResult,
    Reason,
    State,
)
from patterns.confidence_gated_action import ActionGuard, PolicyConfig, decide as cga_decide
from patterns.confidence_gated_action.bedrock import BedrockResult, CallableBedrockFallback


@dataclass
class PolicyVerdict:
    action: Action
    band: Band | None
    reason: Reason
    decided_by: DecidedBy


def _ctx(state: State) -> dict:
    return {
        "has_idempotency_key": state.has_idempotency_key,
        "error_type": state.error_type,
        "error_text": state.error_text,
    }


def decide(
    state: State,
    result: DeciderResult | None,
    *,
    auto_min: float = 0.85,
    review_min: float = 0.60,
    discard_min: float = 0.90,
    bedrock_cap_reached: bool = False,
) -> PolicyVerdict:
    if state.error_type is None and state.error_text is None:
        return PolicyVerdict(
            Action.ESCALATE_HUMAN,
            Band.NONE,
            Reason.MISSING_EVIDENCE,
            DecidedBy.RULE,
        )
    if result is None:
        return PolicyVerdict(
            Action.ESCALATE_HUMAN,
            Band.NONE,
            Reason.DECIDER_UNAVAILABLE,
            DecidedBy.RULE,
        )

    # Evaluate bands/guards without Bedrock (engine calls apply_bedrock separately).
    policy = PolicyConfig(
        auto_min=auto_min,
        review_min=review_min,
        escalate_action=Action.ESCALATE_HUMAN.value,
        guards={
            Action.DISCARD_DUPLICATE.value: ActionGuard(
                min_confidence=discard_min,
                require_attr="has_idempotency_key",
            )
        },
        use_bedrock=False,
    )

    d = cga_decide(
        _ctx(state),
        policy=policy,
        probabilities=dict(result.probabilities),
        choice=result.choice,
        latency_ms=result.latency_ms,
    )

    conf = float(d.top_confidence)
    if conf >= auto_min:
        band = Band.AUTO
    elif conf >= review_min:
        band = Band.REVIEW
    else:
        band = Band.LOW

    if band == Band.LOW:
        return PolicyVerdict(
            Action.ESCALATE_HUMAN, Band.LOW, Reason.LOW_CONFIDENCE, DecidedBy.DECIDER
        )

    if d.path == "rule" and d.bedrock_reason == "guard_failed":
        return PolicyVerdict(
            Action.ESCALATE_HUMAN, band, Reason.DISCARD_GUARD, DecidedBy.RULE
        )

    # With use_bedrock=False, review-band returns escalate+low_confidence OR
    # we still know conf is in review from band calculation above.
    if band == Band.REVIEW:
        # Recover provisional action from Decider choice (pattern escalated because Bedrock off).
        try:
            provisional = Action(result.choice)
        except ValueError:
            return PolicyVerdict(
                Action.ESCALATE_HUMAN,
                band,
                Reason.DECIDER_UNAVAILABLE,
                DecidedBy.RULE,
            )
        # Re-check discard guard for provisional
        if provisional == Action.DISCARD_DUPLICATE and (
            conf < discard_min or not state.has_idempotency_key
        ):
            return PolicyVerdict(
                Action.ESCALATE_HUMAN, band, Reason.DISCARD_GUARD, DecidedBy.RULE
            )
        if bedrock_cap_reached:
            return PolicyVerdict(
                Action.ESCALATE_HUMAN, band, Reason.BEDROCK_CAP, DecidedBy.RULE
            )
        return PolicyVerdict(provisional, band, Reason.AUTO, DecidedBy.DECIDER)

    if d.path == "auto":
        try:
            action = Action(d.action)
        except ValueError:
            return PolicyVerdict(
                Action.ESCALATE_HUMAN,
                Band.LOW,
                Reason.DECIDER_UNAVAILABLE,
                DecidedBy.RULE,
            )
        return PolicyVerdict(action, Band.AUTO, Reason.AUTO, DecidedBy.DECIDER)

    return PolicyVerdict(
        Action.ESCALATE_HUMAN, Band.NONE, Reason.DECIDER_UNAVAILABLE, DecidedBy.RULE
    )


def apply_bedrock(
    verdict: PolicyVerdict,
    bedrock_choice: str | None,
    *,
    valid: bool,
) -> PolicyVerdict:
    if verdict.band != Band.REVIEW:
        return verdict
    if not valid or bedrock_choice is None:
        return PolicyVerdict(
            Action.ESCALATE_HUMAN,
            verdict.band,
            Reason.BEDROCK_INVALID,
            DecidedBy.DECIDER_BEDROCK,
        )

    def _fb(_context, _options, provisional):  # noqa: ANN001
        return BedrockResult(choice=bedrock_choice, reason=None, valid=True)

    policy = PolicyConfig(
        auto_min=0.85,
        review_min=0.60,
        escalate_action=Action.ESCALATE_HUMAN.value,
        guards={},
        use_bedrock=True,
    )
    probs = {a.value: 0.01 for a in Action}
    probs[verdict.action.value] = 0.70

    d = cga_decide(
        {},
        policy=policy,
        probabilities=probs,
        choice=verdict.action.value,
        bedrock=CallableBedrockFallback(_fb),
    )
    if d.path == "bedrock_agreed":
        return PolicyVerdict(
            verdict.action,
            verdict.band,
            Reason.BEDROCK_AGREE,
            DecidedBy.DECIDER_BEDROCK,
        )
    return PolicyVerdict(
        Action.ESCALATE_HUMAN,
        verdict.band,
        Reason.BEDROCK_DISAGREE,
        DecidedBy.DECIDER_BEDROCK,
    )
