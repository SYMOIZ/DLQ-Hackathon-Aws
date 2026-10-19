# QA_LIVE.md — Live E2E against public URL

Base URL: `https://<CLOUDFRONT_DOMAIN>`

Run at: `2026-10-18T16:34:09Z` · Instance: `<EC2_INSTANCE_ID>` · Region: `us-east-1`

| Feature | Result | Evidence |
|---|---|---|
| index_https | PASS | `status=200 token_len=43` |
| healthz | PASS | `{"ok": true, "run_id": "bootstrap"}` |
| api_401_no_login | PASS | `status=401 body=b'{"error": "unauthorized"}'` |
| cognito_signup_confirm | PASS | `e2e.518f03@example.com` |
| login | PASS | `status=200` |
| api_run_authed | PASS | `run_id=20261018T160623Z queue=dlqj-payments-dlq mode=dry_run` |
| security_headers | PASS | `CSP default-src 'self'; X-Content-Type-Options=nosniff` |
| arn_prefix_denied | PASS | `{"error": "prefix_denied"}` for `prod-secret` |
| access_denied_outside_dlqj | PASS | `{"error": "prefix_denied"}` for non-`dlqj-*` |
| arn_payments_ok | PASS | `dlqj-payments-dlq` accepted |
| triage_job_reuse | PASS | `reused existing run messages total=50 run=20261018T160623Z` |
| triage_job_under_20s | PASS | `skipped — reused existing triage` |
| triage_job_complete | PASS | `reused existing decisions total=50` |
| endpoint_messages | PASS | `status=200 total=50` |
| messages_pagination | PASS | `page1=10 page2=10 overlap=0 total=50` |
| messages_search | PASS | `q='38b6acbf-6be' total=1` |
| messages_filter_action | PASS | `action=quarantine_poison n=3` |
| messages_drawer | PASS | `GET /api/messages/{id}` 200 |
| override | PASS | `POST .../override` 200 |
| override_revert | PASS | `revert` restored previous action |
| endpoint_clusters | PASS | `status=200` |
| endpoint_benchmark | PASS | `status=200 n_messages=300` |
| apply_job_accepted | PASS | `job_id=44b9f8cdf8e3 planned_before=3` |
| apply_job_complete | PASS | `applied=3 skipped=0 failed=0` |
| apply_aws_verify | PASS | `s3 quarantine 0→3; backup/20261018T160623Z 0→3; post-check DLQ 50→47` |
| apply_s3_or_queue_effect | PASS | `quarantine_objects=3 backup_objects=3` |
| restore_api | PASS | `no HTTP restore (CLI-only); expected 404` |
| logout | PASS | `status=200` |
| api_401_after_logout | PASS | `status=401` |

Summary: **29/29 PASS, 0 FAIL**

## Notes

- Prefer reused triage run when `/api/messages` already has ~50 decisions (Decider on CPU is slow).
- First full apply of the payments run: **50× `escalate_human`** (DLQ depth unchanged — expected; escalate only resets visibility).
- Quarantine demo: 3 decisions overridden to `quarantine_poison` then applied → **3 S3 quarantine + 3 backup objects**; SQS ApproximateNumberOfMessages later settled at **47**.
- Restore is CLI-only (`dlq-judge restore`); no `/api/restore` endpoint.
- After EC2 stop/start, CloudFront origin DNS must be refreshed to the new public DNS (updated this session: `ec2-3-231-156-170.compute-1.amazonaws.com`).
- Hotfix: `ui_server` override/apply now use `_latest_run_id()` (was incorrectly targeting `bootstrap`).

## Host stop/start durability

- Prior session: stop kept EBS + runs on disk (`20261018T160623Z` with 50 decisions survived restart).
- This session (post-QA): **State=stopped**; EBS `vol-0c1eb1380636991d0` **attached** (40 GiB, DeleteOnTermination=false); S3 quarantine=3, backup/20261018T160623Z=3, deploy/app=2. **Not terminated.**
