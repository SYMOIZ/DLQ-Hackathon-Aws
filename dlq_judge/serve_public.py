"""Public UI entrypoint for systemd (bind 0.0.0.0)."""

from __future__ import annotations

import os
from pathlib import Path

from dlq_judge.config import get_config
from dlq_judge.ui_server import serve


def main() -> None:
    cfg = get_config(reload=True)
    run_id = os.environ.get("DLQJ_RUN_ID")
    if not run_id:
        # Prefer real triage runs over the empty bootstrap placeholder.
        named = [
            p.name
            for p in cfg.runs_dir.iterdir()
            if p.is_dir() and not p.name.startswith("_") and p.name != "bootstrap"
        ]
        if named:
            run_id = sorted(named)[-1]
        elif (cfg.runs_dir / "bootstrap").is_dir():
            run_id = "bootstrap"
    if not run_id:
        run_id = "bootstrap"
        (cfg.runs_dir / run_id).mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("DLQJ_UI_PORT", str(cfg.ui_port)))
    serve(
        cfg,
        run_id,
        allow_apply=os.environ.get("DLQJ_ALLOW_APPLY", "1") == "1",
        port=port,
        bind=os.environ.get("DLQJ_BIND", "0.0.0.0"),
    )


if __name__ == "__main__":
    main()
