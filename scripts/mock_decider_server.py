"""Local Decider stand-in matching POST /v1/systemone when HF weights are unavailable.

Maps error_type heuristics to calibrated choice distributions (same 5 options).
Replace with `strands-decider serve` once Qwen base weights finish downloading.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bench.baseline_rules import RULES

OPTIONS = [
    "redrive_now",
    "redrive_later",
    "quarantine_poison",
    "discard_duplicate",
    "escalate_human",
]


def _decide(state: str) -> dict:
    m = re.search(r"error_type=([^\n]*)", state or "")
    et = (m.group(1).strip() if m else "") or "unknown"
    choice = RULES.get(et, "escalate_human")
    # Band mix: duplicates high (discard guard), timeouts review, validation auto
    peak = {
        "DuplicateDelivery": 0.93,
        "TimeoutError": 0.72,
        "ThrottlingException": 0.70,
        "ValidationError": 0.90,
        "SchemaMismatch": 0.88,
        "TransientNetwork": 0.91,
        "AuthExpired": 0.55,
    }.get(et, 0.80)
    rest = (1.0 - peak) / (len(OPTIONS) - 1)
    probs = {o: rest for o in OPTIONS}
    probs[choice] = peak
    conf = (5 * peak - 1) / 4
    return {
        "choice": choice,
        "confidence": round(conf, 4),
        "probabilities": probs,
        "model": "mock-decider-rules",
        "answers": [
            {
                "choice": choice,
                "confidence": round(conf, 4),
                "probabilities": probs,
            }
        ],
    }


class H(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: ANN002
        pass

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/health"):
            self._json(200, {"status": "ok", "model": "mock-decider-rules"})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/systemone":
            self._json(404, {"error": "not_found"})
            return
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            req = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "bad_json"})
            return
        self._json(200, _decide(req.get("state") or ""))


if __name__ == "__main__":
    httpd = ThreadingHTTPServer(("127.0.0.1", 8000), H)
    print("mock decider on http://127.0.0.1:8000", flush=True)
    httpd.serve_forever()
