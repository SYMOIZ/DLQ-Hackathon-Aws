"""Layer 0: load and validate environment configuration (REQUIREMENTS §7)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def _req(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"config error: required env {name} is missing")
    return v


def _f(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        return float(raw)
    except ValueError as e:
        raise SystemExit(f"config error: {name} must be a float, got {raw!r}") from e


def _i(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        return int(raw)
    except ValueError as e:
        raise SystemExit(f"config error: {name} must be an int, got {raw!r}") from e


@dataclass(frozen=True)
class Config:
    aws_profile: str
    region: str
    stack_name: str
    queue_prefix: str
    source_queue: str
    dlq: str
    bucket: str | None
    bedrock_model_id: str
    bedrock_max_calls: int
    max_clusters: int
    decider_url: str
    decider_model: str
    decider_timeout_s: float
    auto_min: float
    review_min: float
    discard_min: float
    batch_size: int
    redrive_delay_s: int
    runs_dir: Path
    ui_port: int
    cognito_user_pool_id: str | None
    cognito_client_id: str | None


_CONFIG: Config | None = None


def get_config(reload: bool = False) -> Config:
    global _CONFIG
    if _CONFIG is not None and not reload:
        return _CONFIG
    _load_dotenv(Path.cwd() / ".env")
    auto_min = _f("DLQJ_AUTO_MIN", 0.85)
    review_min = _f("DLQJ_REVIEW_MIN", 0.60)
    discard_min = _f("DLQJ_DISCARD_MIN", 0.90)
    if review_min >= auto_min:
        raise SystemExit("config error: DLQJ_REVIEW_MIN must be < DLQJ_AUTO_MIN")
    delay = _i("DLQJ_REDRIVE_DELAY_S", 300)
    if not 60 <= delay <= 900:
        raise SystemExit("config error: DLQJ_REDRIVE_DELAY_S must be 60–900")
    port = _i("DLQJ_UI_PORT", 8765)
    if not 1 <= port <= 65535:
        raise SystemExit("config error: DLQJ_UI_PORT out of range")
    # On EC2, instance role credentials are used when AWS_PROFILE is unset.
    cfg = Config(
        aws_profile=os.environ.get("AWS_PROFILE") or "",
        region=os.environ.get("DLQJ_REGION") or os.environ.get("AWS_DEFAULT_REGION") or _req("DLQJ_REGION"),
        stack_name=os.environ.get("DLQJ_STACK_NAME", "dlq-judge"),
        queue_prefix=os.environ.get("DLQJ_QUEUE_PREFIX", "dlqj-"),
        source_queue=os.environ.get("DLQJ_SOURCE_QUEUE", "dlqj-orders"),
        dlq=os.environ.get("DLQJ_DLQ", "dlqj-orders-dlq"),
        bucket=os.environ.get("DLQJ_BUCKET") or None,
        bedrock_model_id=_req("DLQJ_BEDROCK_MODEL_ID"),
        bedrock_max_calls=_i("DLQJ_BEDROCK_MAX_CALLS", 50),
        max_clusters=_i("DLQJ_MAX_CLUSTERS", 5),
        decider_url=os.environ.get("DLQJ_DECIDER_URL", "http://127.0.0.1:8000"),
        decider_model=os.environ.get(
            "DLQJ_DECIDER_MODEL", "StrandsAgents/strands-decider-2B-hobson-v21"
        ),
        decider_timeout_s=_f("DLQJ_DECIDER_TIMEOUT_S", 120.0),
        auto_min=auto_min,
        review_min=review_min,
        discard_min=discard_min,
        batch_size=_i("DLQJ_BATCH_SIZE", 300),
        redrive_delay_s=delay,
        runs_dir=Path(os.environ.get("DLQJ_RUNS_DIR", "./runs")),
        ui_port=port,
        cognito_user_pool_id=os.environ.get("DLQJ_COGNITO_USER_POOL_ID"),
        cognito_client_id=os.environ.get("DLQJ_COGNITO_CLIENT_ID"),
    )
    _CONFIG = cfg
    return cfg


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)
