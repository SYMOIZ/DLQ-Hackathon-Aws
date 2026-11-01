"""Background triage/apply jobs with JSON progress files (request < 20s)."""

from __future__ import annotations

import json
import os
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dlq_judge import engine
from dlq_judge.config import Config


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def create(self, kind: str, meta: dict[str, Any] | None = None) -> str:
        job_id = uuid.uuid4().hex[:12]
        doc = {
            "job_id": job_id,
            "kind": kind,
            "status": "queued",
            "progress": 0,
            "message": "queued",
            "created_at": _now(),
            "updated_at": _now(),
            "result": None,
            "error": None,
            "meta": meta or {},
        }
        self._write(job_id, doc)
        return job_id

    def _write(self, job_id: str, doc: dict[str, Any]) -> None:
        path = self._path(job_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        tmp.replace(path)

    def update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            doc = self.get(job_id)
            doc.update(fields)
            doc["updated_at"] = _now()
            self._write(job_id, doc)
            return doc

    def get(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        if not path.is_file():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def start(self, job_id: str, fn: Callable[[], Any]) -> None:
        def runner() -> None:
            self.update(job_id, status="running", progress=5, message="started")
            try:
                result = fn()
                self.update(
                    job_id,
                    status="succeeded",
                    progress=100,
                    message="done",
                    result=result,
                )
            except Exception as e:
                self.update(
                    job_id,
                    status="failed",
                    progress=100,
                    message="failed",
                    error=f"{e}\n{traceback.format_exc()[-800:]}",
                )

        if os.environ.get("DLQJ_SYNC_JOBS") == "1":
            runner()  # serverless hosts end background threads with the request
        else:
            threading.Thread(target=runner, daemon=True).start()


def start_triage_job(store: JobStore, cfg: Config, *, apply: bool = False) -> str:
    job_id = store.create("triage", {"apply": apply})

    def work() -> dict[str, Any]:
        store.update(job_id, progress=10, message="triage running")
        run_id = engine.triage(cfg, apply=False)
        store.update(job_id, progress=90, message=f"run {run_id}")
        out: dict[str, Any] = {"run_id": run_id}
        if apply:
            store.update(job_id, progress=92, message="waiting/apply")
            # Apply may need visibility wait — still background
            out["apply"] = engine.apply_run(cfg, run_id, yes=True)
        return out

    store.start(job_id, work)
    return job_id


def start_apply_job(store: JobStore, cfg: Config, run_id: str) -> str:
    job_id = store.create("apply", {"run_id": run_id})

    def work() -> dict[str, Any]:
        store.update(job_id, progress=20, message="apply running")
        result = engine.apply_run(cfg, run_id, yes=True)
        return {"run_id": run_id, **result}

    store.start(job_id, work)
    return job_id
