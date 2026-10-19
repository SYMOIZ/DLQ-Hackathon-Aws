"""Sign up → confirm (needs email code) smoke for Cognito; login + API 401 check."""
from __future__ import annotations

import json
import secrets
import threading
import time
import urllib.error
import urllib.request

from dlq_judge import auth
from dlq_judge.config import get_config
from dlq_judge.ui_server import Handler
from http.server import ThreadingHTTPServer


def main() -> None:
    cfg = get_config(reload=True)
    email = f"dlqj.tester.{secrets.token_hex(3)}@example.com"
    password = "<TEST_PASSWORD>"
    print("signup", email, flush=True)
    try:
        out = auth.sign_up(cfg, email, password)
        print("signup_ok", out, flush=True)
    except auth.AuthError as e:
        print("signup_err", e.code, e.message, flush=True)
        return

    # Start UI server briefly to verify 401 without login
    from pathlib import Path

    run_dirs = sorted(Path("runs").glob("*"))
    run_id = run_dirs[-1].name if run_dirs else "none"
    Handler.cfg = cfg
    Handler.run_id = run_id
    Handler.token = "test-token"
    Handler.allow_apply = False
    httpd = ThreadingHTTPServer(("127.0.0.1", 8766), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    req = urllib.request.Request(
        "http://127.0.0.1:8766/api/run",
        headers={"X-DLQJ-Token": "test-token", "Host": "127.0.0.1:8766"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        print("api_unexpected_200", flush=True)
    except urllib.error.HTTPError as e:
        print("api_without_login", e.code, e.read().decode()[:200], flush=True)
    httpd.shutdown()
    print(
        "NOTE: complete email verify manually then login; signup triggered Cognito email.",
        flush=True,
    )


if __name__ == "__main__":
    main()
