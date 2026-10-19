"""TC-U01–U06"""

from dlq_judge.masking import mask_text
from dlq_judge.state import build_state


def test_u01_email():
    assert "[EMAIL]" in mask_text("mail me at a.b+x@example.com please")
    assert "example.com" not in mask_text("a.b+x@example.com").replace("[EMAIL]", "")


def test_u02_phone():
    assert "[PHONE]" in mask_text("call +1-555-123-4567 now")


def test_u03_number():
    assert "[NUMBER]" in mask_text("card 4111111111111111 ok")
    assert "123456789012" in mask_text("id 123456789012 end")  # 12 digits unchanged


def test_u04_truncate():
    body = "x" * 5000
    st = build_state({"MessageId": "m1", "Body": body, "MessageAttributes": {}})
    assert st.body_masked.endswith("...[truncated]")
    assert len(st.body_masked) == 2000 + len("...[truncated]")


def test_u05_missing_error():
    st = build_state({"MessageId": "m1", "Body": "{}", "MessageAttributes": {}})
    assert st.error_type is None and st.error_text is None


def test_u06_unicode():
    st = build_state(
        {
            "MessageId": "m1",
            "Body": "{not json 你好",
            "MessageAttributes": {
                "error_type": {"StringValue": "X", "DataType": "String"}
            },
        }
    )
    assert "你好" in st.body_masked
