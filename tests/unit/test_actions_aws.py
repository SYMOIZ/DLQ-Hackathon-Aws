"""TC-U21, U26, U27 + allowlist"""

from unittest.mock import MagicMock, patch

import pytest

from dlq_judge import actions, aws_io
from dlq_judge.config import Config


def _cfg(**kw):
    base = dict(
        aws_profile="dlqj",
        region="us-east-1",
        stack_name="dlq-judge",
        queue_prefix="dlqj-",
        source_queue="dlqj-orders",
        dlq="dlqj-orders-dlq",
        bucket="dlqj-quarantine-test",
        bedrock_model_id="amazon.nova-micro-v1:0",
        bedrock_max_calls=50,
        max_clusters=5,
        decider_url="http://127.0.0.1:8000",
        decider_model="x",
        decider_timeout_s=5,
        auto_min=0.85,
        review_min=0.60,
        discard_min=0.90,
        batch_size=300,
        redrive_delay_s=300,
        runs_dir=".",
        ui_port=8765,
        cognito_user_pool_id=None,
        cognito_client_id=None,
    )
    base.update(kw)
    return Config(**base)


def test_u26_allowlist():
    aws_io.assert_allowed("dlqj-orders", "dlqj-")
    with pytest.raises(aws_io.QueueNotAllowed):
        aws_io.assert_allowed("prod-orders", "dlqj-")


def test_u21_backup_before_delete():
    cfg = _cfg()
    order = []

    def put(cfg, key, obj):
        order.append(("put", key))

    def send(cfg, q, body, attrs=None, delay_seconds=0):
        order.append(("send", q))
        return "mid"

    def delete(cfg, q, rh):
        order.append(("delete", q))

    with patch.object(aws_io, "s3_put_json", put), patch.object(
        aws_io, "send_message", send
    ), patch.object(aws_io, "delete_message", delete), patch.object(
        aws_io, "change_visibility", lambda *a, **k: order.append(("vis",))
    ):
        actions.execute(
            cfg,
            action="redrive_now",
            run_id="r1",
            message_id="m1",
            receipt_handle="rh",
            body="{}",
            attributes={},
            decision={},
        )
    assert order[0][0] == "put"
    assert order[1][0] == "send"
    assert order[2][0] == "delete"


def test_u27_backup_failure_skips_delete():
    cfg = _cfg()

    def put(*a, **k):
        raise RuntimeError("s3 down")

    with patch.object(aws_io, "s3_put_json", put), patch.object(
        aws_io, "delete_message"
    ) as dele, patch.object(aws_io, "send_message") as send:
        with pytest.raises(RuntimeError, match="backup"):
            actions.execute(
                cfg,
                action="redrive_now",
                run_id="r1",
                message_id="m1",
                receipt_handle="rh",
                body="{}",
                attributes={},
                decision={},
            )
        send.assert_not_called()
        dele.assert_not_called()
