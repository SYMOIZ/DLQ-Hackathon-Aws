"""Layer 1: build State objects from SQS messages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dlq_judge.masking import mask_text
from dlq_judge.models import State

BODY_MAX = 2000


def _attr(attrs: dict[str, Any], name: str) -> str | None:
    if not attrs or name not in attrs:
        return None
    item = attrs[name]
    if isinstance(item, dict):
        return item.get("StringValue") or item.get("Value")
    return str(item) if item is not None else None


def _attr_num(attrs: dict[str, Any], name: str) -> int | None:
    if not attrs or name not in attrs:
        return None
    item = attrs[name]
    raw = item.get("StringValue") if isinstance(item, dict) else item
    if raw is None and isinstance(item, dict):
        raw = item.get("Value")
    try:
        return int(float(str(raw)))
    except (TypeError, ValueError):
        return None


def truncate_body(body: str) -> str:
    if len(body) <= BODY_MAX:
        return body
    return body[:BODY_MAX] + "...[truncated]"


def build_state(message: dict[str, Any], *, now: datetime | None = None) -> State:
    now = now or datetime.now(timezone.utc)
    attrs = message.get("MessageAttributes") or {}
    body = message.get("Body") or ""
    masked = truncate_body(mask_text(body))
    recv = _attr_num(attrs, "original_receive_count")
    if recv is None:
        sqs_attrs = message.get("Attributes") or {}
        try:
            recv = int(sqs_attrs.get("ApproximateReceiveCount") or 0)
        except ValueError:
            recv = None
    failed_at = _attr(attrs, "failed_at")
    age = None
    if failed_at:
        try:
            ts = datetime.fromisoformat(failed_at.replace("Z", "+00:00"))
            age = max(0, int((now - ts).total_seconds() // 60))
        except ValueError:
            age = None
    return State(
        message_id=message.get("MessageId") or "",
        source_queue=_attr(attrs, "source_queue"),
        receive_count=recv,
        age_minutes=age,
        error_type=_attr(attrs, "error_type"),
        error_text=_attr(attrs, "error_text"),
        has_idempotency_key=bool(_attr(attrs, "idempotency_key")),
        body_masked=masked,
    )
