"""Vercel Function entrypoint: the same UI/API handler as the EC2 server, made stateless.

Runs and jobs live in S3 (DLQJ_STATE_BUCKET) and are mirrored to /tmp per request. AWS access uses
Vercel OIDC federation (AWS_ROLE_ARN + the per-request x-vercel-oidc-token header), so no keys are stored.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DLQJ_RUNS_DIR", "/tmp/dlqj-runs")
os.environ.setdefault("DLQJ_SYNC_JOBS", "1")
os.environ.setdefault("DLQJ_DECIDER_URL", "bedrock")
TOKEN_FILE = "/tmp/vercel-oidc-token"
if os.environ.get("AWS_ROLE_ARN"):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        os.environ.pop(k, None)  # use only the OIDC role, never ambient keys
    os.environ.setdefault("AWS_WEB_IDENTITY_TOKEN_FILE", TOKEN_FILE)
    os.environ.setdefault("AWS_ROLE_SESSION_NAME", "dlqj-vercel")

from dlq_judge import jobs, storage_sync  # noqa: E402
from dlq_judge.config import get_config  # noqa: E402
from dlq_judge.ui_server import Handler  # noqa: E402

cfg = get_config(reload=True)
BUCKET = os.environ.get("DLQJ_STATE_BUCKET", "")
QUEUE_STATE = cfg.runs_dir / "_state" / "queue_override.json"

Handler.cfg = cfg
Handler.run_id = "bootstrap"
Handler.token = os.environ["DLQJ_UI_TOKEN"]
Handler.allow_apply = os.environ.get("DLQJ_ALLOW_APPLY", "1") == "1"
Handler.public_hosts = {h for h in os.environ.get("DLQJ_PUBLIC_HOST", "").lower().split(",") if h}
Handler.account_id = os.environ.get("DLQJ_ACCOUNT_ID", "")
cfg.runs_dir.mkdir(parents=True, exist_ok=True)


class SharedJobStore(jobs.JobStore):
    """Uploads each job update so polls served by other instances see progress."""

    def _write(self, job_id, doc):  # noqa: ANN001
        super()._write(job_id, doc)
        if BUCKET:
            path = self._path(job_id)
            storage_sync._client(cfg).upload_file(str(path), BUCKET, storage_sync.PREFIX + path.relative_to(cfg.runs_dir).as_posix())


Handler.job_store = SharedJobStore(cfg.runs_dir / "_jobs")
DEFAULT_QUEUES = (cfg.dlq, cfg.source_queue)
STATIC = {"/app.css", "/app.js", "/healthz"}


class handler(Handler):  # noqa: N801 - Vercel looks for this name
    def _sync_in(self) -> float:
        token = self.headers.get("x-vercel-oidc-token")
        if token:
            Path(TOKEN_FILE).write_text(token, encoding="utf-8")
        host = (self.headers.get("x-forwarded-host") or self.headers.get("Host") or "").split(":")[0].lower()
        if host.endswith(".vercel.app"):
            Handler.public_hosts.add(host)  # preview and production deployment URLs
        started = storage_sync.now()
        if BUCKET:
            storage_sync.pull(cfg, BUCKET)
        q = json.loads(QUEUE_STATE.read_text(encoding="utf-8")) if QUEUE_STATE.is_file() else None
        Handler.queue_override = q
        object.__setattr__(cfg, "dlq", q["dlq"] if q else DEFAULT_QUEUES[0])
        object.__setattr__(cfg, "source_queue", q["source_queue"] if q else DEFAULT_QUEUES[1])
        return started

    def _sync_out(self, started: float) -> None:
        if Handler.queue_override and not QUEUE_STATE.is_file():
            storage_sync.write_state(cfg.runs_dir, QUEUE_STATE.name, json.dumps(Handler.queue_override))
        elif Handler.queue_override:
            current = QUEUE_STATE.read_text(encoding="utf-8")
            if json.loads(current) != Handler.queue_override:
                storage_sync.write_state(cfg.runs_dir, QUEUE_STATE.name, json.dumps(Handler.queue_override))
        if BUCKET:
            storage_sync.push(cfg, BUCKET, started)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] not in STATIC:
            self._sync_in()
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        started = self._sync_in()
        try:
            super().do_POST()
        finally:
            self._sync_out(started)
