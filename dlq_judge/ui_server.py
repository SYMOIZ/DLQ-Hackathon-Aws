"""Layer 5: UI + JSON API (stdlib). Supports local and CloudFront public deploy."""

from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from dlq_judge import auth, aws_connector, engine, jobs, queues, runlog
from dlq_judge.config import Config

UI_DIR = Path(__file__).resolve().parents[1] / "ui"


def _security_headers(handler: BaseHTTPRequestHandler, *, api: bool = False) -> None:
    handler.send_header(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
    )
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    if api:
        handler.send_header("Cache-Control", "no-store")


def _row(d: dict[str, Any]) -> dict[str, Any]:
    st = d.get("state") or {}
    return {
        "message_id": d.get("message_id"),
        "error_type": st.get("error_type"),
        "receive_count": st.get("receive_count"),
        "action": d.get("action"),
        "confidence": d.get("confidence"),
        "decided_by": d.get("decided_by"),
        "status": d.get("status"),
        "band": d.get("band"),
        "reason": d.get("reason"),
    }


class Handler(BaseHTTPRequestHandler):
    cfg: Config
    run_id: str
    token: str
    allow_apply: bool
    job_store: jobs.JobStore
    public_hosts: set[str]
    account_id: str
    server_version = "dlqj/1.0"
    # optional session override for queue ARN (process-wide for hackathon single-tenant)
    queue_override: dict[str, str] | None = None

    def log_message(self, fmt: str, *args) -> None:  # noqa: ANN002
        pass

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host in ("127.0.0.1", "localhost"):
            return True
        return host in self.public_hosts

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            ohost = urlparse(origin).hostname or ""
        except Exception:
            return False
        ohost = ohost.lower()
        if ohost in ("127.0.0.1", "localhost"):
            return True
        return ohost in self.public_hosts

    def _json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        _security_headers(self, api=True)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        _security_headers(self, api=False)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 4096:
            raise ValueError("body too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _token_ok(self) -> bool:
        return self.headers.get("X-DLQJ-Token") == self.token

    def _cognito_payload(self) -> dict[str, Any] | None:
        hdr = self.headers.get("Authorization") or ""
        token = None
        if hdr.lower().startswith("bearer "):
            token = hdr[7:].strip()
        if not token:
            token = auth.parse_cookie(self.headers.get("Cookie"))
        if not token:
            return None
        try:
            return auth.verify_id_token(self.cfg, token)
        except auth.AuthError:
            return None

    def _require_api(self) -> bool:
        if not self._host_ok() or not self._origin_ok() or not self._token_ok():
            self._json(403, {"error": "forbidden"})
            return False
        if not self._cognito_payload():
            self._json(401, {"error": "unauthorized"})
            return False
        return True

    def _run_candidates(self) -> list[Path]:
        root = self.cfg.runs_dir
        if not root.is_dir():
            return []
        return sorted(
            (
                p
                for p in root.iterdir()
                if p.is_dir() and not p.name.startswith("_") and p.name != "bootstrap"
            ),
            key=lambda p: p.name,
        )

    def _latest_run_id(self) -> str:
        """Prefer newest run that has summary.json; else newest dir; else bootstrap id."""
        candidates = self._run_candidates()
        with_summary = [p for p in candidates if (p / "summary.json").is_file()]
        if with_summary:
            return with_summary[-1].name
        if candidates:
            return candidates[-1].name
        return self.run_id

    def _run_dir(self) -> Path:
        rid = self._latest_run_id()
        self.run_id = rid
        return self.cfg.runs_dir / rid

    def _public_stats(self) -> dict[str, Any]:
        """Unauthenticated summary for the marketing landing hero."""
        empty = {
            "has_run": False,
            "run_id": None,
            "queue": None,
            "mode": None,
            "processed": 0,
            "counts": {},
            "band_counts": {},
            "median_decider_ms": None,
            "bedrock_calls": 0,
            "label": "No triage run yet",
        }
        try:
            rdir = self._run_dir()
        except Exception:
            return empty
        summary_path = rdir / "summary.json"
        if not summary_path.is_file():
            return empty
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        queue = summary.get("queue") or ""
        processed = int(summary.get("processed") or 0)
        return {
            "has_run": processed > 0 or bool(summary.get("run_id")),
            "run_id": summary.get("run_id"),
            "queue": queue,
            "mode": summary.get("mode"),
            "processed": processed,
            "counts": summary.get("counts") or {},
            "band_counts": summary.get("band_counts") or {},
            "median_decider_ms": summary.get("median_decider_ms"),
            "bedrock_calls": int(summary.get("bedrock_calls") or 0),
            "label": f"Last run · {queue}" if queue else "Last run",
        }

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._host_ok():
            self._json(403, {"error": "forbidden"})
            return

        # Public static + auth gate page without Cognito (login UI)
        if path in ("/", "/index.html"):
            html = (UI_DIR / "index.html").read_text(encoding="utf-8")
            html = html.replace("{{DLQJ_TOKEN}}", self.token)
            html = html.replace("{{DLQJ_RUN_ID}}", self.run_id)
            html = html.replace(
                "{{DLQJ_COGNITO_CLIENT_ID}}", self.cfg.cognito_client_id or ""
            )
            self._text(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/app.css":
            self._text(200, (UI_DIR / "app.css").read_bytes(), "text/css")
            return
        if path == "/app.js":
            self._text(200, (UI_DIR / "app.js").read_bytes(), "application/javascript")
            return
        if path == "/healthz":
            self._json(200, {"ok": True, "run_id": self.run_id})
            return
        if path == "/api/public/stats":
            try:
                self._json(200, self._public_stats())
            except Exception as e:
                self._json(500, {"error": str(e)})
            return

        if path.startswith("/api/"):
            if not self._require_api():
                return
            try:
                self._handle_api_get(path, parsed)
            except Exception as e:
                self._json(500, {"error": str(e)})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not self._host_ok() or not self._origin_ok():
            self._json(403, {"error": "forbidden"})
            return
        ctype = self.headers.get("Content-Type", "")
        if "application/json" not in ctype:
            self._json(403, {"error": "forbidden"})
            return
        try:
            body = self._read_json()
        except Exception:
            self._json(400, {"error": "bad_request"})
            return

        if path == "/api/auth/signup":
            try:
                out = auth.sign_up(
                    self.cfg, body.get("email", ""), body.get("password", "")
                )
                self._json(200, out)
            except auth.AuthError as e:
                self._json(400, {"error": e.code, "message": e.message})
            return
        if path == "/api/auth/confirm":
            try:
                auth.confirm_sign_up(
                    self.cfg, body.get("email", ""), body.get("code", "")
                )
                self._json(200, {"ok": True})
            except auth.AuthError as e:
                self._json(400, {"error": e.code, "message": e.message})
            return
        if path == "/api/auth/resend":
            try:
                out = auth.resend_confirmation_code(
                    self.cfg, body.get("email", "")
                )
                self._json(200, out)
            except auth.AuthError as e:
                self._json(400, {"error": e.code, "message": e.message})
            return
        if path == "/api/auth/login":
            try:
                tokens = auth.login(
                    self.cfg, body.get("email", ""), body.get("password", "")
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                _security_headers(self, api=True)
                secure = (
                    "; Secure"
                    if (self.headers.get("X-Forwarded-Proto") == "https"
                        or "cloudfront" in (self.headers.get("Host") or "").lower())
                    else ""
                )
                self.send_header(
                    "Set-Cookie",
                    f"dlqj_id={tokens['id_token']}; Path=/; HttpOnly; SameSite=Lax{secure}",
                )
                payload = json.dumps(
                    {"ok": True, "id_token": tokens["id_token"]}
                ).encode()
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except auth.AuthError as e:
                self._json(401, {"error": e.code, "message": e.message})
            return
        if path == "/api/auth/logout":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            _security_headers(self, api=True)
            self.send_header(
                "Set-Cookie",
                "dlqj_id=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax; Secure",
            )
            payload = b'{"ok":true}'
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path == "/api/auth/delete-profile":
            if not self._host_ok() or not self._origin_ok() or not self._token_ok():
                self._json(403, {"error": "forbidden"})
                return
            claims = self._cognito_payload()
            if not claims:
                self._json(401, {"error": "unauthorized"})
                return
            email = (
                str(claims.get("email") or claims.get("cognito:username") or "")
            ).strip()
            if not email:
                self._json(400, {"error": "no_email", "message": "No email on token"})
                return
            try:
                auth.delete_user(self.cfg, email)
            except auth.AuthError as e:
                self._json(400, {"error": e.code, "message": e.message})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            _security_headers(self, api=True)
            self.send_header(
                "Set-Cookie",
                "dlqj_id=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax; Secure",
            )
            payload = b'{"ok":true}'
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if not self._require_api():
            return
        try:
            self._handle_api_post(path, body)
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _handle_api_get(self, path: str, parsed) -> None:  # noqa: ANN001
        rdir = self._run_dir()
        if path == "/api/aws/connector":
            try:
                self._json(200, aws_connector.connector_status(self.cfg))
            except Exception as e:
                self._json(500, {"error": str(e), "ok": False})
            return
        if path == "/api/run":
            if not (rdir / "summary.json").is_file():
                self._json(
                    200,
                    {
                        "run_id": self.run_id,
                        "queue": self.cfg.dlq,
                        "mode": "dry_run",
                        "processed": 0,
                        "counts": {},
                        "status_counts": {},
                        "actionable_count": 0,
                        "thresholds": {
                            "auto_min": self.cfg.auto_min,
                            "review_min": self.cfg.review_min,
                            "discard_min": self.cfg.discard_min,
                            "bedrock_max_calls": self.cfg.bedrock_max_calls,
                        },
                        "decider_model": self.cfg.decider_model,
                        "bedrock_model_id": self.cfg.bedrock_model_id,
                        "queue_override": Handler.queue_override,
                    },
                )
                return
            summary = json.loads((rdir / "summary.json").read_text(encoding="utf-8"))
            summary["queue_override"] = Handler.queue_override
            self._json(200, summary)
            return
        if path == "/api/messages":
            qs = parse_qs(parsed.query)
            page = max(1, int((qs.get("page") or ["1"])[0]))
            page_size = min(100, max(1, int((qs.get("page_size") or ["50"])[0])))
            q = ((qs.get("q") or [""])[0]).lower()
            fa = (qs.get("action") or [""])[0]
            fs = (qs.get("status") or [""])[0]
            decisions = runlog.load_decisions(rdir / "decisions.jsonl")
            rows = [_row(d) for d in decisions]
            if q:
                rows = [
                    r
                    for r in rows
                    if q in (r.get("message_id") or "").lower()
                    or q in (r.get("error_type") or "").lower()
                ]
            if fa:
                rows = [r for r in rows if r.get("action") == fa]
            if fs:
                rows = [r for r in rows if r.get("status") == fs]
            total = len(rows)
            start = (page - 1) * page_size
            items = rows[start : start + page_size]
            self._json(
                200,
                {
                    "items": items,
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                },
            )
            return
        if path.startswith("/api/messages/"):
            mid = path[len("/api/messages/") :]
            decisions = runlog.load_decisions(rdir / "decisions.jsonl")
            for d in decisions:
                if d.get("message_id") == mid:
                    self._json(200, d)
                    return
            self._json(404, {"error": "not_found"})
            return
        if path == "/api/clusters":
            p = rdir / "clusters.json"
            if p.is_file():
                self._json(200, json.loads(p.read_text(encoding="utf-8")))
            else:
                self._json(200, {"schema_version": 1, "items": []})
            return
        if path == "/api/benchmark":
            real = Path("bench/results/results.json")
            if real.is_file():
                data = json.loads(real.read_text(encoding="utf-8"))
                data["sample_data"] = False
                self._json(200, data)
            else:
                self._json(200, {"sample_data": False, "approaches": []})
            return
        if path.startswith("/api/jobs/"):
            jid = path[len("/api/jobs/") :]
            try:
                self._json(200, self.job_store.get(jid))
            except KeyError:
                self._json(404, {"error": "not_found"})
            return
        self._json(404, {"error": "not_found"})

    def _handle_api_post(self, path: str, body: dict[str, Any]) -> None:
        if path == "/api/queue":
            arn = body.get("dlq_arn") or body.get("arn") or ""
            try:
                parsed = queues.parse_and_validate(
                    arn,
                    expected_account=self.account_id,
                    expected_region=self.cfg.region,
                    prefix=self.cfg.queue_prefix,
                )
            except queues.QueueArnError as e:
                self._json(400, {"error": str(e)})
                return
            # Derive source queue guess: strip -dlq suffix if present
            source = parsed.name
            if source.endswith("-dlq"):
                source = source[: -len("-dlq")]
            Handler.queue_override = {
                "dlq": parsed.name,
                "source_queue": source,
                "dlq_arn": parsed.arn,
            }
            # mutate live config via env + reload pattern: update object fields
            object.__setattr__(self.cfg, "dlq", parsed.name)
            object.__setattr__(self.cfg, "source_queue", source)
            self._json(200, {"ok": True, "queue": Handler.queue_override})
            return
        if path == "/api/aws/connector/test":
            try:
                out = aws_connector.test_role_arn(
                    self.cfg, str(body.get("role_arn") or "")
                )
                self._json(200, out)
            except Exception as e:
                self._json(400, {"ok": False, "error": str(e)})
            return
        if path == "/api/jobs/triage":
            jid = jobs.start_triage_job(
                self.job_store, self.cfg, apply=bool(body.get("apply"))
            )
            self._json(202, {"job_id": jid})
            return
        if path == "/api/jobs/apply":
            if not self.allow_apply:
                self._json(403, {"error": "apply_disabled"})
                return
            run_id = body.get("run_id") or self._latest_run_id()
            self.run_id = run_id
            jid = jobs.start_apply_job(self.job_store, self.cfg, run_id)
            self._json(202, {"job_id": jid})
            return
        if path.endswith("/override") and path.startswith("/api/messages/"):
            mid = path[len("/api/messages/") : -len("/override")]
            try:
                rid = self._latest_run_id()
                self.run_id = rid
                if body.get("revert"):
                    updated = engine.override_message(
                        self.cfg, rid, mid, action=None, revert=True
                    )
                else:
                    updated = engine.override_message(
                        self.cfg,
                        rid,
                        mid,
                        action=body.get("action"),
                        revert=False,
                    )
                self._json(200, updated)
            except KeyError:
                self._json(404, {"error": "not_found"})
            except ValueError:
                self._json(400, {"error": "bad_request"})
            except RuntimeError as e:
                self._json(409, {"error": "conflict", "message": str(e)})
            return
        if path == "/api/run/apply":
            # Prefer async job; keep sync only if expected count tiny — still spawn job
            if not self.allow_apply:
                self._json(403, {"error": "apply_disabled"})
                return
            if body.get("confirm") != "APPLY":
                self._json(400, {"error": "bad_request"})
                return
            jid = jobs.start_apply_job(self.job_store, self.cfg, self.run_id)
            self._json(202, {"job_id": jid, "async": True})
            return
        self._json(404, {"error": "not_found"})


def serve(
    cfg: Config,
    run_id: str,
    *,
    allow_apply: bool = False,
    port: int = 8765,
    bind: str = "127.0.0.1",
) -> None:
    token = os.environ.get("DLQJ_UI_TOKEN") or secrets.token_urlsafe(32)
    public = os.environ.get("DLQJ_PUBLIC_HOST", "").strip().lower()
    hosts = {h for h in public.split(",") if h}
    account = os.environ.get("DLQJ_ACCOUNT_ID") or ""
    if not account:
        try:
            from dlq_judge.aws_io import session

            account = session(cfg).client("sts").get_caller_identity()["Account"]
        except Exception:
            account = ""

    Handler.cfg = cfg
    Handler.run_id = run_id
    Handler.token = token
    Handler.allow_apply = allow_apply
    Handler.job_store = jobs.JobStore(cfg.runs_dir / "_jobs")
    Handler.public_hosts = hosts
    Handler.account_id = account
    httpd = ThreadingHTTPServer((bind, port), Handler)
    print(
        f"UI http://{bind}:{port}/  run={run_id}  public_hosts={sorted(hosts)}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
