import json
import urllib.request

payload = {
    "state": (
        "error_type=TimeoutError\nerror_text=upstream timeout\n"
        "receive_count=2\nage_minutes=5\nsource_queue=dlqj-orders\n"
        "has_idempotency_key=false\nbody={}"
    ),
    "questions": [
        {
            "type": "choice",
            "question": "What is the safest next action for this failed message?",
            "options": [
                "redrive_now",
                "redrive_later",
                "quarantine_poison",
                "discard_duplicate",
                "escalate_human",
            ],
        }
    ],
}
req = urllib.request.Request(
    "http://127.0.0.1:8000/v1/systemone",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    print(resp.read().decode()[:2000])
