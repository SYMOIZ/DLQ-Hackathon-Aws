"""Layer 3: execute recovery actions with S3 backup ordering."""

from __future__ import annotations

from typing import Any

from dlq_judge import aws_io
from dlq_judge.config import Config
from dlq_judge.models import Action


def _backup(cfg: Config, run_id: str, message_id: str, payload: dict[str, Any]) -> None:
    aws_io.s3_put_json(cfg, f"backup/{run_id}/{message_id}.json", payload)


def execute(
    cfg: Config,
    *,
    action: str,
    run_id: str,
    message_id: str,
    receipt_handle: str,
    body: str,
    attributes: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    payload = {
        "body": body,
        "attributes": attributes,
        "decision": decision,
        "message_id": message_id,
    }
    act = Action(action)
    if act == Action.ESCALATE_HUMAN:
        aws_io.change_visibility(cfg, cfg.dlq, receipt_handle, 0)
        return

    try:
        _backup(cfg, run_id, message_id, payload)
    except Exception as e:
        raise RuntimeError(f"backup: {e}") from e

    try:
        if act == Action.REDRIVE_NOW:
            aws_io.send_message(cfg, cfg.source_queue, body, attributes)
        elif act == Action.REDRIVE_LATER:
            aws_io.send_message(
                cfg, cfg.source_queue, body, attributes, delay_seconds=cfg.redrive_delay_s
            )
        elif act == Action.QUARANTINE_POISON:
            aws_io.s3_put_json(cfg, f"quarantine/{run_id}/{message_id}.json", payload)
        elif act == Action.DISCARD_DUPLICATE:
            pass
        else:
            raise RuntimeError(f"unknown action {action}")
    except Exception as e:
        raise RuntimeError(f"send: {e}") from e

    try:
        aws_io.delete_message(cfg, cfg.dlq, receipt_handle)
    except Exception as e:
        raise RuntimeError(f"delete: {e}") from e
