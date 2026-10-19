"""Approach A: deterministic rule baseline."""

from __future__ import annotations

from typing import Any

RULES = {
    "TimeoutError": "redrive_later",
    "ThrottlingException": "redrive_later",
    "ValidationError": "quarantine_poison",
    "SchemaMismatch": "quarantine_poison",
    "DuplicateDelivery": "discard_duplicate",
    "TransientNetwork": "redrive_now",
    "AuthExpired": "escalate_human",
}


def decide_rules(record: dict[str, Any]) -> str:
    attrs = record.get("attributes") or {}
    et = attrs.get("error_type") or (record.get("state") or {}).get("error_type")
    return RULES.get(et, "escalate_human")
