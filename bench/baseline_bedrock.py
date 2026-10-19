"""Approach B: Bedrock-only baseline (one Converse call per message)."""

from __future__ import annotations

from typing import Any

from dlq_judge import bedrock_client
from dlq_judge.config import Config
from dlq_judge.models import State
from dlq_judge.state import build_state


def decide_bedrock(cfg: Config, record: dict[str, Any]) -> tuple[str, int]:
    if "Body" in record or "MessageId" in record:
        state = build_state(record)
    else:
        attrs = record.get("attributes") or {}
        state = State(
            message_id=str(record.get("fixture_id") or "x"),
            source_queue=attrs.get("source_queue"),
            receive_count=int(attrs.get("original_receive_count") or 1),
            age_minutes=5,
            error_type=attrs.get("error_type"),
            error_text=attrs.get("error_text"),
            has_idempotency_key=bool(attrs.get("idempotency_key")),
            body_masked=str(record.get("body") or "")[:2000],
        )
    br = bedrock_client.second_opinion(cfg, state, "escalate_human")
    choice = br.get("choice") or "escalate_human"
    return choice, int(br.get("latency_ms") or 0)
