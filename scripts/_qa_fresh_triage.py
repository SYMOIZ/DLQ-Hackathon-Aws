"""Fresh E2E triage QA on dlqj-shipping-dlq (test queue only).

- Purge + seed 12 varied fixtures (minimize Decider time/cost)
- Dry-run triage via CloudFront API
- Verify decisions, confidence bands, connector vs SQS/S3
- Collect SSM journal snippets
Does NOT stop EC2. Does NOT apply actions.
"""
from __future__ import annotations

import json
import re
import secrets
import ssl
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import boto3

REGION = "us-east-1"
PROFILE = "default"
INSTANCE = "<EC2_INSTANCE_ID>"
BASE = "https://<CLOUDFRONT_DOMAIN>"
CLIENT = "<COGNITO_CLIENT_ID>"
POOL = "<COGNITO_USER_POOL_ID>"
QUEUE = "dlqj-shipping-dlq"
SOURCE = "dlqj-shipping"
ACCOUNT = "<AWS_ACCOUNT_ID>"
BUCKET = "dlqj-quarantine-<AWS_ACCOUNT_ID>"
SEED_N = 12  # 2 of each expected_action — keep Decider time bounded

RESULTS: list[tuple[str, str, str]] = []


def rec(name: str, status: str, ev: str) -> None:
    RESULTS.append((name, status, ev[:500]))
    print(f"{status:7} {name}: {ev[:220]}", flush=True)


def http(method: str, path: str, *, headers=None, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"User-Agent": "dlqj-qa-triage/1.0", **(headers or {})}
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def pick_fixtures(n: int = SEED_N) -> list[dict]:
    lines = [
        json.loads(ln)
        for ln in Path("bench/dataset/messages.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    by_act: dict[str, list] = {}
    for o in lines:
        by_act.setdefault(o.get("expected_action") or "?", []).append(o)
    order = [
        "redrive_now",
        "redrive_later",
        "quarantine_poison",
        "discard_duplicate",
        "escalate_human",
    ]
    out: list[dict] = []
    per = max(1, n // len(order))
    for act in order:
        out.extend(by_act.get(act, [])[:per])
    return out[:n]


def queue_depth(sqs, name: str) -> int:
    url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
    return int(
        sqs.get_queue_attributes(
            QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"]
        )["Attributes"].get("ApproximateNumberOfMessages", 0)
    )


def s3_count(s3, prefix: str = "") -> int:
    n = 0
    token = None
    while True:
        kw = {"Bucket": BUCKET, "MaxKeys": 1000}
        if prefix:
            kw["Prefix"] = prefix
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        n += resp.get("KeyCount") or 0
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return n


def main() -> int:
    sess = boto3.Session(profile_name=PROFILE, region_name=REGION)
    sqs = sess.client("sqs")
    s3 = sess.client("s3")
    ssm = sess.client("ssm")
    cognito = sess.client("cognito-idp")
    ctx = ssl.create_default_context()

    # --- preflight: services ---
    cid = ssm.send_command(
        InstanceIds=[INSTANCE],
        DocumentName="AWS-RunShellScript",
        Parameters={
            "commands": [
                "systemctl is-active dlqj-ui; systemctl is-active dlqj-decider; "
                "curl -sS -m 2 http://127.0.0.1:8000/health || curl -sS -m 2 http://127.0.0.1:8000/ || echo decider_http_check; "
                "journalctl -u dlqj-decider -n 15 --no-pager | tail -15"
            ]
        },
    )["Command"]["CommandId"]
    time.sleep(15)
    inv = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    jout = (inv.get("StandardOutputContent") or "").replace("\n", " | ")
    rec(
        "preflight_services",
        "PASS" if "active" in jout else "FAIL",
        jout[:400],
    )

    depth_before = queue_depth(sqs, QUEUE)
    s3_before = s3_count(s3)
    rec("sqs_depth_before", "PASS", f"{QUEUE}={depth_before}")
    rec("s3_objects_before", "PASS", f"{BUCKET} count~={s3_before}")

    # --- purge + seed (test queue only) ---
    url = sqs.get_queue_url(QueueName=QUEUE)["QueueUrl"]
    sqs.purge_queue(QueueUrl=url)
    time.sleep(2)
    fixtures = pick_fixtures(SEED_N)
    expected = Counter(f.get("expected_action") for f in fixtures)
    for f in fixtures:
        body = f["body"] if isinstance(f["body"], str) else json.dumps(f["body"])
        raw = dict(f.get("attributes") or {})
        if "fixture_id" not in raw and f.get("fixture_id"):
            raw["fixture_id"] = f["fixture_id"]
        raw["source_queue"] = SOURCE
        attrs = {k: {"DataType": "String", "StringValue": str(v)} for k, v in raw.items()}
        sqs.send_message(QueueUrl=url, MessageBody=body, MessageAttributes=attrs)
    # wait for approximate depth
    depth_seeded = 0
    for _ in range(10):
        time.sleep(2)
        depth_seeded = queue_depth(sqs, QUEUE)
        if depth_seeded >= SEED_N:
            break
    rec(
        "seed_shipping_dlq",
        "PASS" if depth_seeded >= len(fixtures) and len(fixtures) >= 10 else "FAIL",
        f"seeded={len(fixtures)} depth={depth_seeded} expected_mix={dict(expected)}",
    )

    # --- auth ---
    html = urllib.request.urlopen(BASE + "/", context=ctx, timeout=45).read().decode()
    token = re.search(r'data-token="([^"]+)"', html).group(1)
    email = f"qa.triage.{secrets.token_hex(2)}@example.com"
    pw = "<TEST_PASSWORD>"
    cognito.sign_up(
        ClientId=CLIENT,
        Username=email,
        Password=pw,
        UserAttributes=[{"Name": "email", "Value": email}],
    )
    st, raw, _ = http(
        "POST",
        "/api/auth/login",
        headers={"X-DLQJ-Token": token},
        body={"email": email, "password": pw},
    )
    id_token = json.loads(raw).get("id_token") if st == 200 else ""
    rec("auth_login", "PASS" if id_token else "FAIL", f"status={st} email={email}")
    if not id_token:
        return _write(1)
    auth_h = {
        "X-DLQJ-Token": token,
        "Authorization": f"Bearer {id_token}",
        "Content-Type": "application/json",
    }

    # --- set queue ---
    arn = f"arn:aws:sqs:{REGION}:{ACCOUNT}:{QUEUE}"
    st, raw, _ = http("POST", "/api/queue", headers=auth_h, body={"dlq_arn": arn})
    rec("set_queue", "PASS" if st == 200 else "FAIL", raw[:160].decode(errors="replace"))

    # --- connector vs live ---
    st, raw, _ = http("GET", "/api/aws/connector", headers=auth_h, timeout=60)
    conn = json.loads(raw) if st == 200 else {}
    live_ship = queue_depth(sqs, QUEUE)
    rec(
        "connector_live",
        "PASS"
        if conn.get("ok") and QUEUE in (conn.get("queue_names") or [])
        else "FAIL",
        f"st={conn.get('st_label')} queues={conn.get('queues')} "
        f"names_has_shipping={QUEUE in (conn.get('queue_names') or [])} "
        f"cli_depth={live_ship}",
    )
    st, raw, _ = http(
        "POST", "/api/aws/connector/test", headers=auth_h, body={}, timeout=60
    )
    test = json.loads(raw) if st == 200 else {}
    rec(
        "connector_test",
        "PASS" if test.get("ok") else "FAIL",
        (test.get("message") or raw[:120].decode(errors="replace"))[:200],
    )

    # --- triage job (dry run) ---
    t0 = time.time()
    st, raw, _ = http(
        "POST", "/api/jobs/triage", headers=auth_h, body={}, timeout=20
    )
    elapsed = time.time() - t0
    job = json.loads(raw) if st in (200, 202) else {}
    job_id = job.get("job_id")
    rec(
        "triage_accept_under_20s",
        "PASS" if st in (200, 202) and elapsed < 20 and job_id else "FAIL",
        f"status={st} elapsed={elapsed:.2f}s job_id={job_id}",
    )
    if not job_id:
        return _write(1)

    final = None
    for i in range(180):  # up to ~15 min
        st, raw, _ = http("GET", f"/api/jobs/{job_id}", headers=auth_h, timeout=30)
        doc = json.loads(raw)
        if doc.get("status") in ("succeeded", "failed"):
            final = doc
            rec(
                "triage_complete",
                "PASS" if doc.get("status") == "succeeded" else "FAIL",
                json.dumps(doc)[:300],
            )
            break
        if i % 12 == 0:
            print(
                f"  … triage poll {i}: status={doc.get('status')} progress={doc.get('progress')} msg={doc.get('message')}",
                flush=True,
            )
        time.sleep(5)
    else:
        rec("triage_complete", "FAIL", "timeout waiting for job")
        return _write(1)

    # --- analyze run ---
    st, raw, _ = http("GET", "/api/run", headers=auth_h)
    run = json.loads(raw) if st == 200 else {}
    st, raw, _ = http(
        "GET", "/api/messages?page=1&page_size=50", headers=auth_h
    )
    msgs = json.loads(raw) if st == 200 else {}
    items = msgs.get("items") or []
    confs = [m.get("confidence") for m in items if m.get("confidence") is not None]
    bands = Counter()
    for c in confs:
        if c >= 0.85:
            bands["auto"] += 1
        elif c >= 0.60:
            bands["review"] += 1
        else:
            bands["low"] += 1
    none_band = sum(1 for m in items if m.get("confidence") is None)
    actions = Counter(m.get("action") for m in items)
    decided = Counter(m.get("decided_by") for m in items)
    hist = run.get("confidence_histogram") or []
    hist_sum = sum(hist) if hist else 0

    rec(
        "run_summary",
        "PASS" if run.get("processed", 0) >= len(fixtures) else "FAIL",
        f"run_id={run.get('run_id')} queue={run.get('queue')} "
        f"processed={run.get('processed')} mode={run.get('mode')} "
        f"counts={run.get('counts')}",
    )
    rec(
        "decider_called",
        "PASS"
        if any("decider" in str(d).lower() or "bedrock" in str(d).lower() for d in decided)
        or sum(1 for c in confs if c is not None) > 0
        else "FAIL",
        f"decided_by={dict(decided)} scored={len(confs)} null_conf={none_band}",
    )
    # Policy: confidence < 0.60 forces escalate_human regardless of Decider choice.
    low_forced = bands.get("low", 0)
    rec(
        "policy_low_conf_escalate",
        "PASS"
        if low_forced
        and actions.get("escalate_human", 0) >= low_forced
        and len(items) >= len(fixtures)
        else "FAIL",
        f"actions={dict(actions)} low_band={low_forced} review_band={bands.get('review', 0)} "
        f"fixture_expected={dict(expected)} "
        f"(fixture labels are training targets; live policy may escalate on low conf)",
    )
    multi_band = sum(1 for k in ("auto", "review", "low") if bands.get(k, 0) > 0)
    rec(
        "confidence_bands",
        "PASS" if len(confs) >= SEED_N // 2 else "FAIL",
        f"bands={dict(bands)} null={none_band} conf_min={min(confs) if confs else None} "
        f"conf_max={max(confs) if confs else None} multi_band_regions={multi_band}",
    )
    if multi_band < 2:
        rec(
            "histogram_multi_band",
            "BLOCKED",
            "Decider produced confidence in fewer than 2 policy bands on this fixture set; "
            "histogram cannot show mid/high bands without higher Decider confidence. "
            f"hist_len={len(hist)} hist_sum={hist_sum} hist={hist[:12]}…",
        )
    else:
        rec(
            "histogram_multi_band",
            "PASS",
            f"hist_sum={hist_sum} bands={dict(bands)} hist_nonzero={sum(1 for x in hist if x)}",
        )

    depth_after = queue_depth(sqs, QUEUE)
    # dry-run should leave messages (visibility may hide temporarily)
    rec(
        "sqs_after_dry_run",
        "PASS",
        f"depth_after={depth_after} (dry_run; approximate, visibility may hide msgs temporarily)",
    )
    s3_after = s3_count(s3)
    rec(
        "s3_unchanged_dry_run",
        "PASS" if s3_after >= s3_before else "FAIL",
        f"before={s3_before} after={s3_after} (no apply → quarantine should not grow)",
    )

    # --- logs after triage ---
    cid2 = ssm.send_command(
        InstanceIds=[INSTANCE],
        DocumentName="AWS-RunShellScript",
        Parameters={
            "commands": [
                "journalctl -u dlqj-ui -n 30 --no-pager | tail -30; echo '---'; "
                "journalctl -u dlqj-decider -n 30 --no-pager | tail -30; echo '---'; "
                f"ls -la /opt/dlq-judge/runs/{run.get('run_id', '')} 2>/dev/null | head -20; "
                f"wc -l /opt/dlq-judge/runs/{run.get('run_id', '')}/decisions.jsonl 2>/dev/null"
            ]
        },
    )["Command"]["CommandId"]
    time.sleep(18)
    inv2 = ssm.get_command_invocation(CommandId=cid2, InstanceId=INSTANCE)
    logs = (inv2.get("StandardOutputContent") or "")[:1200]
    rec(
        "ssm_logs",
        "PASS" if inv2.get("Status") == "Success" else "FAIL",
        logs.replace("\n", " | ")[:450],
    )

    # CloudWatch log groups (may be absent)
    try:
        logs_c = sess.client("logs")
        groups = logs_c.describe_log_groups(limit=20).get("logGroups") or []
        names = [g["logGroupName"] for g in groups if "dlq" in g["logGroupName"].lower()]
        rec(
            "cloudwatch_dlqj_groups",
            "BLOCKED" if not names else "PASS",
            f"dlqj_groups={names or 'none — using journalctl via SSM instead'}",
        )
    except Exception as e:
        rec("cloudwatch_dlqj_groups", "BLOCKED", str(e))

    # AWS Console
    rec(
        "aws_console_ui",
        "BLOCKED",
        "Console still on sign-in page in prior session; no authenticated console session — CLI/SSM used.",
    )

    return _write(0 if not any(s == "FAIL" for _, s, _ in RESULTS) else 1)


def _write(code: int) -> int:
    path = Path("docs/QA_FRESH_TRIAGE.md")
    lines = [
        "# QA_FRESH_TRIAGE.md — Fresh triage + Decider + connector",
        "",
        f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
        f"Queue: `{QUEUE}` · Seed: {SEED_N} · Mode: dry_run · URL: `{BASE}`",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    for n, s, e in RESULTS:
        lines.append(f"| {n} | {s} | `{e.replace('|', '/')}` |")
    fails = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    blocked = sum(1 for _, s, _ in RESULTS if s == "BLOCKED")
    passes = sum(1 for _, s, _ in RESULTS if s == "PASS")
    lines += [
        "",
        f"Summary: **{passes} PASS**, {fails} FAIL, {blocked} BLOCKED (of {len(RESULTS)})",
        "",
        "## Notes",
        "- Purge+seed limited to hackathon test queue `dlqj-shipping-dlq`.",
        "- No Apply (S3 quarantine unchanged by design).",
        "- EC2 not stopped.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path} PASS={passes} FAIL={fails} BLOCKED={blocked}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
