# Reusable Strands Decider 2B decision pattern: Confidence-gated action with LLM fallback
"""Pluggable Bedrock (or any LLM) fallback interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BedrockResult:
    choice: str | None
    reason: str | None = None
    valid: bool = True
    latency_ms: int = 0


class BedrockFallback(Protocol):
    """Implement this to swap models or disable fallback."""

    def second_opinion(
        self,
        context: Any,
        options: tuple[str, ...],
        provisional: str,
    ) -> BedrockResult: ...


class NullBedrockFallback:
    """Disables Bedrock: review-band decisions escalate."""

    def second_opinion(
        self,
        context: Any,
        options: tuple[str, ...],
        provisional: str,
    ) -> BedrockResult:
        return BedrockResult(choice=None, reason="bedrock_disabled", valid=False, latency_ms=0)


class CallableBedrockFallback:
    """Wrap a plain callable(context, options, provisional) -> BedrockResult | str."""

    def __init__(self, fn: Any) -> None:
        self._fn = fn

    def second_opinion(
        self,
        context: Any,
        options: tuple[str, ...],
        provisional: str,
    ) -> BedrockResult:
        out = self._fn(context, options, provisional)
        if isinstance(out, BedrockResult):
            return out
        if isinstance(out, str):
            return BedrockResult(choice=out, reason=None, valid=True)
        if out is None:
            return BedrockResult(choice=None, reason="empty", valid=False)
        raise TypeError(f"bedrock callable returned {type(out)}")
