"""Layer 2: Bedrock Converse — second opinion and cluster explain."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from dlq_judge.aws_io import session
from dlq_judge.config import Config
from dlq_judge.models import ACTIONS_ORDER, State
from patterns.failed_message_recovery.question import OPTIONS, QUESTION, render_state

_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def _converse(cfg: Config, system: str, user: str) -> tuple[str, int]:
    client = session(cfg).client("bedrock-runtime")
    t0 = time.perf_counter()
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.converse(
                modelId=cfg.bedrock_model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": 512, "temperature": 0.0},
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            parts = resp.get("output", {}).get("message", {}).get("content") or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
            return text, latency_ms
        except Exception as e:
            last_err = e
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"bedrock converse failed: {last_err}")


def second_opinion(cfg: Config, state: State, proposed: str) -> dict[str, Any]:
    system = (
        "You are a careful SQS DLQ triage reviewer. Reply with ONLY a JSON object "
        ' {"choice":"<one of the options>","reason":"<short>"} . '
        f"Options: {', '.join(OPTIONS)}. No markdown."
    )
    user = (
        f"Question: {QUESTION}\n"
        f"Proposed by Decider: {proposed}\n"
        f"State:\n{render_state(state)}\n"
        "Pick the safest action."
    )
    text, latency_ms = _converse(cfg, system, user)
    data = _extract_json(text)
    valid_choices = {a.value for a in ACTIONS_ORDER}
    if not data or data.get("choice") not in valid_choices:
        return {
            "choice": None,
            "reason": (data or {}).get("reason", text[:200]),
            "latency_ms": latency_ms,
            "valid": False,
        }
    return {
        "choice": data["choice"],
        "reason": str(data.get("reason") or ""),
        "latency_ms": latency_ms,
        "valid": True,
    }


def explain_cluster(
    cfg: Config,
    *,
    error_type: str,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    sample_ids = [s.get("message_id") for s in samples]
    brief = []
    for s in samples[:5]:
        st = s.get("state") or {}
        brief.append(
            {
                "message_id": s.get("message_id"),
                "error_text": st.get("error_text"),
                "receive_count": st.get("receive_count"),
                "body_masked": (st.get("body_masked") or "")[:400],
            }
        )
    system = (
        "You analyze clusters of quarantined SQS DLQ messages. Reply with ONLY JSON: "
        '{"root_cause":"...","suggested_fix":"...","claims":[{"text":"...","evidence_ids":["id"]}],'
        '"unverified":false}. Evidence IDs must be from the provided sample message_ids.'
    )
    user = json.dumps({"error_type": error_type, "samples": brief}, ensure_ascii=False)
    text, latency_ms = _converse(cfg, system, user)
    data = _extract_json(text) or {}
    allowed = set(sample_ids)
    claims = []
    unverified = False
    for c in data.get("claims") or []:
        if not isinstance(c, dict):
            continue
        ids = [i for i in (c.get("evidence_ids") or []) if i in allowed]
        if len(ids) != len(c.get("evidence_ids") or []):
            unverified = True
        claims.append({"text": str(c.get("text") or ""), "evidence_ids": ids})
    if not claims and data.get("root_cause"):
        claims = [{"text": str(data["root_cause"]), "evidence_ids": list(sample_ids)[:1]}]
    return {
        "root_cause": str(data.get("root_cause") or ""),
        "suggested_fix": str(data.get("suggested_fix") or ""),
        "claims": claims,
        "unverified": bool(data.get("unverified")) or unverified,
        "latency_ms": latency_ms,
        "sample_ids": sample_ids,
    }
