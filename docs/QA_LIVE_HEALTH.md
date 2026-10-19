# QA_LIVE_HEALTH.md — Hands-on live QA

Generated: `2026-10-19T14:05:12.200200+00:00`
URL: `https://<CLOUDFRONT_DOMAIN>` · Instance: `<EC2_INSTANCE_ID>` · Region: `us-east-1`

| Check | Result | Evidence |
|---|---|---|
| ec2_running | PASS | `state=running dns=ec2-44-220-92-81.compute-1.amazonaws.com vol=vol-0c1eb1380636991d0` |
| ssm_online | PASS | `ping=Online` |
| cfn_stack | PASS | `status=UPDATE_COMPLETE` |
| cf_origin_match | PASS | `origin=ec2-44-220-92-81.compute-1.amazonaws.com ec2_dns=ec2-44-220-92-81.compute-1.amazonaws.com` |
| sqs_queues | PASS | `dlqj-orders=46; dlqj-orders-dlq=300; dlqj-payments=0; dlqj-payments-dlq=47; dlqj-shipping=0; dlqj-shipping-dlq=50` |
| s3_quarantine | PASS | `bucket=dlqj-quarantine-<AWS_ACCOUNT_ID> sample_keys=5` |
| s3_deploy | PASS | `bucket=dlqj-deploy-<AWS_ACCOUNT_ID> sample_keys=5` |
| cognito_pool | PASS | `name=dlqj-users status=None` |
| public_landing | PASS | `len=35135 landing=True connector_btn=True` |
| csrf_token | PASS | `len=43` |
| healthz | PASS | `{"ok": true, "run_id": "20261018T172236Z"}` |
| public_stats | PASS | `{"has_run": true, "run_id": "20261018T160623Z", "queue": "dlqj-payments-dlq", "processed": 50, "label": "Last run \u00b7 dlqj-payments-dlq"}` |
| auth_login | PASS | `email=qa.c58d24@example.com` |
| api_401 | PASS | `status=401` |
| api_run | PASS | `run_id=20261018T160623Z queue=dlqj-payments-dlq processed=50` |
| api_messages | PASS | `keys=['items', 'page', 'page_size', 'total']` |
| api_clusters | PASS | `keys=['schema_version', 'items', 'bedrock_calls']` |
| api_benchmark | PASS | `keys=['schema_version', 'sample_data', 'n_messages', 'approaches']` |
| api_connector | PASS | `{"st_label": "Connected", "account_id": "<AWS_ACCOUNT_ID>", "queues": 6, "role_name": "dlqj-ec2"}` |
| arn_deny | PASS | `{"error": "prefix_denied"}` |
| arn_allow | PASS | `{"ok": true, "queue": {"dlq": "dlqj-payments-dlq", "source_queue": "dlqj-payments", "dlq_arn": "arn:aws:sqs:us-east-1:<AWS_ACCOUNT_ID>:dlqj-payments-dlq"}}` |
| connector_test | PASS | `Instance role active · account <AWS_ACCOUNT_ID> · 6 dlqj-* queues` |
| systemd_services | PASS | `active / active / {"ok": true, "run_id": "20261018T172236Z"}20261018T160623Z / 20261018T172235Z / 20261018T172236Z / _jobs / bootstrap / ` |

Summary: **23/23 PASS**, 0 FAIL

---

## Continuation (2026-10-19) — not a re-run of the table above

Fresh triage / Decider / histogram / connector SQS-S3: see **`docs/QA_FRESH_TRIAGE.md`** and updated **`docs/QA_HANDS_ON.md`**.

| Follow-up | Result |
|---|---|
| Fresh dry-run triage on `dlqj-shipping-dlq` (10 msgs) | PASS · run `20261019T150635Z` |
| Decider SystemOne 200s in journal | PASS · 10× POST `/v1/systemone` |
| Confidence multi-band (low+review) | PASS |
| AWS Console UI | BLOCKED (no login session) |
| EC2 stop | Not requested / not done |
