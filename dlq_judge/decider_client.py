"""Layer 2: HTTP client for Strands Decider 2B (urllib)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from dlq_judge.config import Config
from dlq_judge.models import ACTIONS_ORDER, DeciderResult, State
from patterns.failed_message_recovery.question import OPTIONS, QUESTION, render_state

# Short criteria help the Decider separate options (ARCHITECTURE / Decider schema).
CRITERIA: dict[str, str] = {
    "redrive_now": "Transient failure; safe to retry immediately to the source queue.",
    "redrive_later": "Backoff / throttle; retry to the source queue after a delay.",
    "quarantine_poison": "Poison or schema bug; move aside for engineering fix.",
    "discard_duplicate": "Confirmed duplicate with an idempotency key; safe to drop.",
    "escalate_human": "Ambiguous or high-risk; leave for a human.",
}


def confidence_from_pmax(p_max: float, n: int = 5) -> float:
    if n <= 1:
        return p_max
    return (n * p_max - 1.0) / (n - 1.0)


def build_request(state: State) -> dict[str, Any]:
    return {
        "state": render_state(state),
        "model": "strands-decider-latest",
        "questions": {
            "action": {
                "type": "choice",
                "instructions": QUESTION,
                "criteria": {k: CRITERIA[k] for k in OPTIONS},
            }
        },
    }


def _parse_response(data: dict[str, Any], latency_ms: int) -> DeciderResult:
    ans: dict[str, Any] = {}
    answers = data.get("answers")
    if isinstance(answers, dict) and "action" in answers:
        ans = answers["action"] or {}
    elif isinstance(answers, list) and answers:
        ans = answers[0] if isinstance(answers[0], dict) else {}
    else:
        ans = data

    choice = ans.get("choice") or data.get("choice")
    probs = ans.get("probabilities") or data.get("probabilities") or {}
    if isinstance(probs, list) and len(probs) == len(OPTIONS):
        probs = {OPTIONS[i]: float(probs[i]) for i in range(len(OPTIONS))}
    if choice is None and probs:
        choice = max(probs, key=probs.get)
    if choice is None:
        raise ValueError("no choice in decider response")
    choice = str(choice)
    if choice not in {a.value for a in ACTIONS_ORDER}:
        lower = choice.lower().replace(" ", "_")
        for a in ACTIONS_ORDER:
            if a.value == lower:
                choice = a.value
                break
    full_probs = {a.value: float(probs.get(a.value, 0.0)) for a in ACTIONS_ORDER}
    if sum(full_probs.values()) <= 0 and choice in full_probs:
        full_probs[choice] = 1.0
    p_max = max(full_probs.values()) if full_probs else 0.0
    conf = ans.get("confidence", data.get("confidence"))
    if conf is None:
        conf = confidence_from_pmax(p_max)
    else:
        conf = float(conf)
    return DeciderResult(
        choice=choice,
        probabilities=full_probs,
        confidence=conf,
        latency_ms=latency_ms,
    )


def ask(state: State, cfg: Config) -> DeciderResult:
    payload = build_request(state)
    url = cfg.decider_url.rstrip("/") + "/v1/systemone"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=cfg.decider_timeout_s) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ConnectionError(str(e)) from e
    latency_ms = int((time.perf_counter() - t0) * 1000)
    data = json.loads(raw)
    return _parse_response(data, latency_ms)
