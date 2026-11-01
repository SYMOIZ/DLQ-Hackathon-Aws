"""Mirror the runs directory to S3 so stateless hosts (Vercel Functions) share runs and jobs."""

from __future__ import annotations

import time
from pathlib import Path

from dlq_judge.aws_io import session
from dlq_judge.config import Config

PREFIX = "runs/"
_etags: dict[str, str] = {}


def _client(cfg: Config):
    return session(cfg).client("s3")


def pull(cfg: Config, bucket: str) -> None:
    """Download objects that changed since the last pull into cfg.runs_dir."""
    s3 = _client(cfg)
    root = cfg.runs_dir
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(PREFIX) :]
            if not rel or rel.endswith("/") or ".." in rel:
                continue
            dest = root / rel
            if _etags.get(key) == obj["ETag"] and dest.is_file():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(dest))
            _etags[key] = obj["ETag"]
    root.mkdir(parents=True, exist_ok=True)


def push(cfg: Config, bucket: str, since: float) -> None:
    """Upload files under cfg.runs_dir modified at or after `since` (epoch seconds)."""
    s3 = _client(cfg)
    root = cfg.runs_dir
    if not root.is_dir():
        return
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix == ".tmp" or path.stat().st_mtime < since - 1:
            continue
        key = PREFIX + path.relative_to(root).as_posix()
        s3.upload_file(str(path), bucket, key)
        _etags[key] = s3.head_object(Bucket=bucket, Key=key)["ETag"]


def now() -> float:
    return time.time()


def write_state(root: Path, name: str, text: str) -> None:
    p = root / "_state" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
