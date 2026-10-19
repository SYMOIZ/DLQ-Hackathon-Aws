"""Layer 0: dataclasses and enums (ARCHITECTURE §5)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any


class Action(str, Enum):
    REDRIVE_NOW = "redrive_now"
    REDRIVE_LATER = "redrive_later"
    QUARANTINE_POISON = "quarantine_poison"
    DISCARD_DUPLICATE = "discard_duplicate"
    ESCALATE_HUMAN = "escalate_human"


ACTIONS_ORDER: tuple[Action, ...] = (
    Action.REDRIVE_NOW,
    Action.REDRIVE_LATER,
    Action.QUARANTINE_POISON,
    Action.DISCARD_DUPLICATE,
    Action.ESCALATE_HUMAN,
)

ACTION_LABELS = {
    Action.REDRIVE_NOW: "Redrive now",
    Action.REDRIVE_LATER: "Redrive later",
    Action.QUARANTINE_POISON: "Quarantine",
    Action.DISCARD_DUPLICATE: "Discard duplicate",
    Action.ESCALATE_HUMAN: "Escalate to human",
}


class Band(str, Enum):
    AUTO = "auto"
    REVIEW = "review"
    LOW = "low"
    NONE = "none"


class DecidedBy(str, Enum):
    DECIDER = "decider"
    DECIDER_BEDROCK = "decider_bedrock"
    RULE = "rule"


class Reason(str, Enum):
    AUTO = "auto"
    BEDROCK_AGREE = "bedrock_agree"
    BEDROCK_DISAGREE = "bedrock_disagree"
    BEDROCK_INVALID = "bedrock_invalid"
    BEDROCK_CAP = "bedrock_cap"
    LOW_CONFIDENCE = "low_confidence"
    MISSING_EVIDENCE = "missing_evidence"
    DISCARD_GUARD = "discard_guard"
    DECIDER_UNAVAILABLE = "decider_unavailable"


class Status(str, Enum):
    PLANNED = "planned"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"


class RunMode(str, Enum):
    DRY_RUN = "dry_run"
    APPLIED = "applied"


REASON_TO_DECIDED_BY: dict[Reason, DecidedBy] = {
    Reason.AUTO: DecidedBy.DECIDER,
    Reason.LOW_CONFIDENCE: DecidedBy.DECIDER,
    Reason.BEDROCK_AGREE: DecidedBy.DECIDER_BEDROCK,
    Reason.BEDROCK_DISAGREE: DecidedBy.DECIDER_BEDROCK,
    Reason.BEDROCK_INVALID: DecidedBy.DECIDER_BEDROCK,
    Reason.MISSING_EVIDENCE: DecidedBy.RULE,
    Reason.DISCARD_GUARD: DecidedBy.RULE,
    Reason.DECIDER_UNAVAILABLE: DecidedBy.RULE,
    Reason.BEDROCK_CAP: DecidedBy.RULE,
}


def to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    return obj


@dataclass
class State:
    message_id: str
    source_queue: str | None
    receive_count: int | None
    age_minutes: int | None
    error_type: str | None
    error_text: str | None
    has_idempotency_key: bool
    body_masked: str


@dataclass
class DeciderResult:
    choice: str
    probabilities: dict[str, float]
    confidence: float
    latency_ms: int


@dataclass
class BedrockOpinion:
    choice: str
    reason: str
    agrees: bool
    latency_ms: int


@dataclass
class OverrideInfo:
    action: str
    previous_action: str
    at: str
    reason: str = "human"


@dataclass
class DecisionRecord:
    schema_version: int
    run_id: str
    message_id: str
    fixture_id: str | None
    received_index: int
    state: State
    choice: str | None
    confidence: float | None
    probabilities: dict[str, float] | None
    band: str | None
    decider_ms: int | None
    bedrock: BedrockOpinion | None
    decided_by: str
    reason: str
    action: str
    override: OverrideInfo | None
    status: str
    status_detail: str | None
    applied_at: str | None
    # retained for apply matching
    receipt_handle: str | None = None
    raw_body: str | None = None
    raw_attributes: dict[str, Any] = field(default_factory=dict)
