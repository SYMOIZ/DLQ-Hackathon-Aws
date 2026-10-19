"""Layer 5: Strands agent wired with FailedMessageRecoveryGuard."""

from __future__ import annotations

from dlq_judge.config import Config
from dlq_judge.models import State
from patterns.failed_message_recovery.hook import FailedMessageRecoveryGuard


def run_agent(cfg: Config, prompt: str = "") -> int:
    """Run a minimal agent. Returns 0 on success (deny path counts as success)."""
    state = State(
        message_id="agent-demo",
        source_queue=cfg.source_queue,
        receive_count=5,
        age_minutes=10,
        error_type="ValidationError",
        error_text="schema mismatch",
        has_idempotency_key=False,
        body_masked='{"order":1}',
    )
    guard = FailedMessageRecoveryGuard(cfg, state=state)

    # Simulate a discard tool call that policy should deny
    event = {
        "tool_name": "discard_duplicate",
        "tool_input": {
            "message_id": state.message_id,
            "error_type": state.error_type,
            "error_text": state.error_text,
            "receive_count": state.receive_count,
            "age_minutes": state.age_minutes,
            "idempotency_key": None,
            "body": state.body_masked,
        },
    }
    result = guard.before_tool_call(event)
    denied = False
    if isinstance(result, dict) and result.get("intervene") == "deny":
        denied = True
    elif getattr(result, "intervene", None) == "deny":
        denied = True

    # Optional: try real Strands Agent if available
    try:
        from strands import Agent
        from strands.models import BedrockModel

        model = BedrockModel(model_id=cfg.bedrock_model_id)
        agent = Agent(model=model, hooks=[guard])
        # Keep call short; guard is the contract under test
        _ = agent  # constructed OK
        print("agent: strands Agent constructed with guard")
    except Exception as e:
        print(f"agent: strands wiring note: {e}")

    if denied:
        print(f"agent: discard denied ({getattr(result, 'reason', result.get('reason') if isinstance(result, dict) else '')})")
        return 0
    print("agent: unexpected allow")
    return 1
