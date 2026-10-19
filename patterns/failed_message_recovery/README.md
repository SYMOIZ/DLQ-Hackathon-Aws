# Failed message recovery pattern

Copy this folder. Wire Decider + policy in ≤ 10 lines:

```python
from patterns.failed_message_recovery.question import QUESTION, OPTIONS, render_state
from patterns.failed_message_recovery.policy import decide
from patterns.failed_message_recovery.hook import FailedMessageRecoveryGuard

# 1) render_state(state) → Decider choice question (OPTIONS)
# 2) verdict = decide(state, result, auto_min=0.85, review_min=0.60, discard_min=0.90)
# 3) agent.hooks.append(FailedMessageRecoveryGuard(cfg, state))
```

Thresholds: auto ≥ 0.85 act; review 0.60–0.85 Bedrock agree; low escalate. Discard needs confidence ≥ 0.90 and an idempotency key.
