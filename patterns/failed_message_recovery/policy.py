"""decide() — confidence bands and discard guard."""

from __future__ import annotations

from dataclasses import dataclass

from dlq_judge.models import (
    Action,
    Band,
    DecidedBy,
    DeciderResult,
    Reason,
    REASON_TO_DECIDED_BY,
    State,
)


@dataclass
class PolicyVerdict:
    action: Action
    band: Band | None
    reason: Reason
    decided_by: DecidedBy


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

    choice = result.choice
    try:
        action = Action(choice)
    except ValueError:
        return PolicyVerdict(
            Action.ESCALATE_HUMAN,
            Band.LOW,
            Reason.DECIDER_UNAVAILABLE,
            DecidedBy.RULE,
        )

    conf = result.confidence
    if conf >= auto_min:
        band = Band.AUTO
    elif conf >= review_min:
        band = Band.REVIEW
    else:
        band = Band.LOW

    if band == Band.LOW:
        return PolicyVerdict(
            Action.ESCALATE_HUMAN, band, Reason.LOW_CONFIDENCE, DecidedBy.DECIDER
        )

    if action == Action.DISCARD_DUPLICATE:
        if conf < discard_min or not state.has_idempotency_key:
            return PolicyVerdict(
                Action.ESCALATE_HUMAN, band, Reason.DISCARD_GUARD, DecidedBy.RULE
            )

    if band == Band.REVIEW:
        if bedrock_cap_reached:
            return PolicyVerdict(
                Action.ESCALATE_HUMAN, band, Reason.BEDROCK_CAP, DecidedBy.RULE
            )
        # Caller must run Bedrock; provisional escalate until confirmed
        return PolicyVerdict(action, band, Reason.AUTO, DecidedBy.DECIDER)

    return PolicyVerdict(action, band, Reason.AUTO, DecidedBy.DECIDER)


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
    if bedrock_choice == verdict.action.value:
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
