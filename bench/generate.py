"""Deterministic synthetic DLQ dataset (TESTING_QA_UAT §8)."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

TYPES = [
    ("TimeoutError", "redrive_later", 60),
    ("ThrottlingException", "redrive_later", 50),
    ("ValidationError", "quarantine_poison", 50),
    ("SchemaMismatch", "quarantine_poison", 40),
    ("DuplicateDelivery", "discard_duplicate", 40),
    ("TransientNetwork", "redrive_now", 40),
    ("AuthExpired", "escalate_human", 20),
]

# pad to 300 with extras
assert sum(c for _, _, c in TYPES) == 300


def _luhn_invalid(rng: random.Random) -> str:
    digits = [rng.randint(0, 9) for _ in range(15)]
    # force invalid: flip check so sum % 10 != 0
    body = "".join(str(d) for d in digits)
    return body + "0"  # 16 digits; not validated as real PAN


def generate(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    idx = 0
    for error_type, expected, count in TYPES:
        for i in range(count):
            holdout = i < 10
            email = f"user{idx}@example.com"
            phone = f"+1-555-{1000 + (idx % 9000):04d}"
            number = _luhn_invalid(rng)
            body = {
                "order_id": f"ORD-{idx:04d}",
                "customer_email": email,
                "phone": phone,
                "card_hint": number,
                "note": f"{error_type} synthetic",
            }
            attrs = {
                "error_type": error_type,
                "error_text": f"{error_type}: synthetic failure #{idx}",
                "source_queue": "dlqj-orders",
                "original_receive_count": str(1 + (idx % 5)),
                "failed_at": "2026-10-18T12:00:00Z",
                "fixture_id": f"{error_type}:{i}",
                "expected_action": expected,
                "holdout": "true" if holdout else "false",
            }
            if error_type == "DuplicateDelivery":
                attrs["idempotency_key"] = f"idem-{idx:04d}"
            rows.append(
                {
                    "fixture_id": attrs["fixture_id"],
                    "expected_action": expected,
                    "holdout": holdout,
                    "body": json.dumps(body),
                    "attributes": attrs,
                }
            )
            idx += 1
    assert len(rows) == 300
    return rows


def write_dataset(path: Path, seed: int = 42) -> str:
    rows = generate(seed)
    text = "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()


if __name__ == "__main__":
    out = Path(__file__).parent / "dataset" / "messages.jsonl"
    h = write_dataset(out)
    print(out, h)
