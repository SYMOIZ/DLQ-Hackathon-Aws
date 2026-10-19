"""FailedMessageRecoveryGuard — InterventionHandler for Strands agents."""

from __future__ import annotations

from typing import Any

from dlq_judge.config import Config
from dlq_judge.decider_client import ask
from dlq_judge.models import Action, State
from dlq_judge.policy import decide
from patterns.failed_message_recovery.question import OPTIONS

try:
    from strands.handlers import InterventionHandler
except Exception:  # pragma: no cover — import path may vary
    try:
        from strands.agent.interrupt import InterventionHandler  # type: ignore
    except Exception:

        class InterventionHandler:  # type: ignore
            pass


TOOL_TO_ACTION = {
    "redrive_now": Action.REDRIVE_NOW.value,
    "redrive_later": Action.REDRIVE_LATER.value,
    "quarantine_poison": Action.QUARANTINE_POISON.value,
    "discard_duplicate": Action.DISCARD_DUPLICATE.value,
    "escalate_human": Action.ESCALATE_HUMAN.value,
}


class FailedMessageRecoveryGuard(InterventionHandler):
    """Deny tool calls that disagree with Decider + policy."""

    def __init__(self, cfg: Config, state: State | None = None):
        self.cfg = cfg
        self.state = state

    def before_tool_call(self, event: Any) -> Any:
        tool_name = getattr(event, "tool_name", None) or (
            event.get("tool_name") if isinstance(event, dict) else None
        )
        tool_input = getattr(event, "tool_input", None) or (
            event.get("tool_input") if isinstance(event, dict) else {}
        )
        if tool_name not in TOOL_TO_ACTION:
            return event
        state = self.state
        if state is None and isinstance(tool_input, dict):
            # minimal state from tool input
            state = State(
                message_id=str(tool_input.get("message_id") or "unknown"),
                source_queue=tool_input.get("source_queue"),
                receive_count=tool_input.get("receive_count"),
                age_minutes=tool_input.get("age_minutes"),
                error_type=tool_input.get("error_type"),
                error_text=tool_input.get("error_text"),
                has_idempotency_key=bool(tool_input.get("idempotency_key")),
                body_masked=str(tool_input.get("body") or "")[:2000],
            )
        if state is None:
            return _deny(event, "missing state")
        try:
            result = ask(state, self.cfg)
        except Exception:
            result = None
        verdict = decide(
            state,
            result,
            auto_min=self.cfg.auto_min,
            review_min=self.cfg.review_min,
            discard_min=self.cfg.discard_min,
            bedrock_cap_reached=True,  # agent path: no Bedrock second opinion
        )
        allowed = verdict.action.value
        requested = TOOL_TO_ACTION[tool_name]
        if requested != allowed:
            return _deny(event, f"policy={allowed} tool={requested}")
        return event


def _deny(event: Any, reason: str) -> Any:
    # Prefer structured deny if the SDK supports it
    if hasattr(event, "deny"):
        return event.deny(reason)
    if isinstance(event, dict):
        event["intervene"] = "deny"
        event["reason"] = reason
        return event

    class _Denied:
        intervene = "deny"
        reason = ""

    d = _Denied()
    d.reason = reason
    return d
