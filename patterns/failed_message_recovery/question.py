"""QUESTION, OPTIONS, and render_state() for Decider."""

from __future__ import annotations

from dlq_judge.models import ACTIONS_ORDER, Action, State

QUESTION = "What is the safest next action for this failed message?"

OPTIONS: list[str] = [a.value for a in ACTIONS_ORDER]

assert OPTIONS == [
    "redrive_now",
    "redrive_later",
    "quarantine_poison",
    "discard_duplicate",
    "escalate_human",
]


def render_state(state: State) -> str:
    """Compact state text for Decider (masked, truncated)."""
    return (
        f"error_type={state.error_type or ''}\n"
        f"error_text={state.error_text or ''}\n"
        f"receive_count={state.receive_count}\n"
        f"age_minutes={state.age_minutes}\n"
        f"source_queue={state.source_queue or ''}\n"
        f"has_idempotency_key={str(state.has_idempotency_key).lower()}\n"
        f"body={state.body_masked}"
    )
