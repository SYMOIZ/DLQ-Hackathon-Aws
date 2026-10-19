# Reusable Strands Decider 2B decision pattern: Confidence-gated action with LLM fallback
"""Confidence bands + optional Bedrock fallback + per-action guards."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .bedrock import BedrockFallback, BedrockResult, NullBedrockFallback
from .question import DlqAction, OptionSet, dlq_option_set


class DeciderClient(Protocol):
    """Returns choice + probability map from Strands Decider 2B (or mock)."""

    def ask(
        self,
        context: Any,
        option_set: OptionSet,
    ) -> tuple[str, dict[str, float], int]:
        """Return (top_choice, probabilities, latency_ms)."""
        ...


@dataclass(frozen=True)
class ActionGuard:
    """Per-action rule. Example: discard needs ≥0.90 and an idempotency key."""

    min_confidence: float | None = None
    require_attr: str | None = None  # context attribute that must be truthy


@dataclass
class PolicyConfig:
    auto_min: float = 0.85
    review_min: float = 0.60
    escalate_action: str = DlqAction.ESCALATE_HUMAN.value
    guards: dict[str, ActionGuard] = field(default_factory=dict)
    use_bedrock: bool = True

    @staticmethod
    def dlq_defaults() -> "PolicyConfig":
        return PolicyConfig(
            auto_min=0.85,
            review_min=0.60,
            escalate_action=DlqAction.ESCALATE_HUMAN.value,
            guards={
                DlqAction.DISCARD_DUPLICATE.value: ActionGuard(
                    min_confidence=0.90,
                    require_attr="has_idempotency_key",
                )
            },
            use_bedrock=True,
        )


@dataclass(frozen=True)
class Decision:
    action: str
    probabilities: dict[str, float]
    path: str  # auto | bedrock_agreed | bedrock_disagreed | low_confidence | rule
    latency_ms: int
    bedrock_reason: str | None = None
    top_confidence: float = 0.0


def _attr(context: Any, name: str) -> Any:
    if context is None:
        return None
    if isinstance(context, dict):
        return context.get(name)
    return getattr(context, name, None)


def _passes_guard(action: str, conf: float, context: Any, policy: PolicyConfig) -> bool:
    guard = policy.guards.get(action)
    if guard is None:
        return True
    if guard.min_confidence is not None and conf < guard.min_confidence:
        return False
    if guard.require_attr is not None and not _attr(context, guard.require_attr):
        return False
    return True


def decide(
    context: Any,
    options: OptionSet | None = None,
    policy: PolicyConfig | None = None,
    *,
    decider: DeciderClient | Callable[..., tuple[str, dict[str, float], int]] | None = None,
    bedrock: BedrockFallback | None = None,
    probabilities: dict[str, float] | None = None,
    choice: str | None = None,
    latency_ms: int = 0,
) -> Decision:
    """
    Confidence-gated action with optional LLM fallback.

    Prefer injecting a live Decider via ``decider=``. For unit tests, pass
    ``probabilities=`` / ``choice=`` directly (skips the Decider call).
    """
    option_set = options or dlq_option_set()
    cfg = policy or PolicyConfig.dlq_defaults()
    t0 = time.perf_counter()
    total_latency = latency_ms

    if probabilities is None:
        if decider is None:
            return Decision(
                action=cfg.escalate_action,
                probabilities={},
                path="rule",
                latency_ms=0,
                bedrock_reason="decider_unavailable",
                top_confidence=0.0,
            )
        if callable(decider) and not hasattr(decider, "ask"):
            choice, probabilities, d_lat = decider(context, option_set)
        else:
            choice, probabilities, d_lat = decider.ask(context, option_set)  # type: ignore[union-attr]
        total_latency += int(d_lat)

    probs = {o: float(probabilities.get(o, 0.0)) for o in option_set.options}
    if not probs:
        return Decision(
            action=cfg.escalate_action,
            probabilities={},
            path="rule",
            latency_ms=int((time.perf_counter() - t0) * 1000) + total_latency,
            bedrock_reason="empty_probabilities",
            top_confidence=0.0,
        )

    top = choice or max(probs, key=probs.get)
    if top not in probs:
        top = max(probs, key=probs.get)
    conf = float(probs[top])

    if conf < cfg.review_min:
        return Decision(
            action=cfg.escalate_action,
            probabilities=probs,
            path="low_confidence",
            latency_ms=int((time.perf_counter() - t0) * 1000) + total_latency,
            top_confidence=conf,
        )

    if not _passes_guard(top, conf, context, cfg):
        return Decision(
            action=cfg.escalate_action,
            probabilities=probs,
            path="rule",
            latency_ms=int((time.perf_counter() - t0) * 1000) + total_latency,
            bedrock_reason="guard_failed",
            top_confidence=conf,
        )

    if conf >= cfg.auto_min:
        return Decision(
            action=top,
            probabilities=probs,
            path="auto",
            latency_ms=int((time.perf_counter() - t0) * 1000) + total_latency,
            top_confidence=conf,
        )

    # Uncertain band: optional Bedrock agreement required
    if not cfg.use_bedrock:
        return Decision(
            action=cfg.escalate_action,
            probabilities=probs,
            path="low_confidence",
            latency_ms=int((time.perf_counter() - t0) * 1000) + total_latency,
            bedrock_reason="bedrock_disabled",
            top_confidence=conf,
        )

    fb: BedrockFallback = bedrock or NullBedrockFallback()
    br: BedrockResult = fb.second_opinion(context, option_set.options, top)
    total_latency += int(br.latency_ms)

    if not br.valid or br.choice is None:
        return Decision(
            action=cfg.escalate_action,
            probabilities=probs,
            path="bedrock_disagreed",
            latency_ms=int((time.perf_counter() - t0) * 1000) + total_latency,
            bedrock_reason=br.reason or "invalid",
            top_confidence=conf,
        )

    if br.choice == top:
        return Decision(
            action=top,
            probabilities=probs,
            path="bedrock_agreed",
            latency_ms=int((time.perf_counter() - t0) * 1000) + total_latency,
            bedrock_reason=br.reason,
            top_confidence=conf,
        )

    return Decision(
        action=cfg.escalate_action,
        probabilities=probs,
        path="bedrock_disagreed",
        latency_ms=int((time.perf_counter() - t0) * 1000) + total_latency,
        bedrock_reason=br.reason or f"chose_{br.choice}",
        top_confidence=conf,
    )
