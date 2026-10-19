# Reusable Strands Decider 2B decision pattern: Confidence-gated action with LLM fallback
"""Typed question and option sets for Decider choice questions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence


class DlqAction(str, Enum):
    """Default DLQ Judge option set (five actions)."""

    REDRIVE_NOW = "redrive_now"
    REDRIVE_LATER = "redrive_later"
    QUARANTINE_POISON = "quarantine_poison"
    DISCARD_DUPLICATE = "discard_duplicate"
    ESCALATE_HUMAN = "escalate_human"


DLQ_QUESTION = "What is the safest next action for this failed message?"

DLQ_OPTIONS: tuple[str, ...] = tuple(a.value for a in DlqAction)

DLQ_CRITERIA: dict[str, str] = {
    "redrive_now": "Transient failure; safe to retry immediately to the source queue.",
    "redrive_later": "Backoff / throttle; retry to the source queue after a delay.",
    "quarantine_poison": "Poison or schema bug; move aside for engineering fix.",
    "discard_duplicate": "Confirmed duplicate with an idempotency key; safe to drop.",
    "escalate_human": "Ambiguous or high-risk; leave for a human.",
}


@dataclass(frozen=True)
class OptionSet:
    """Generic Decider question + options (caller-supplied domain)."""

    question: str
    options: tuple[str, ...]
    criteria: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if len(self.options) < 2:
            raise ValueError("OptionSet needs at least 2 options")
        if len(set(self.options)) != len(self.options):
            raise ValueError("OptionSet options must be unique")


def dlq_option_set() -> OptionSet:
    return OptionSet(question=DLQ_QUESTION, options=DLQ_OPTIONS, criteria=dict(DLQ_CRITERIA))


def make_option_set(
    question: str,
    options: Sequence[str] | Iterable[str],
    criteria: dict[str, str] | None = None,
) -> OptionSet:
    """Generic factory: pass your own question and options."""
    opts = tuple(options)
    return OptionSet(question=question, options=opts, criteria=criteria)
