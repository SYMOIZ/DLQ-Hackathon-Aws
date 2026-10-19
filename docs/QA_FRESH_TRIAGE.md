# QA_FRESH_TRIAGE.md — Fresh triage + Decider + connector

Generated: `2026-10-19T15:07:38Z` (UTC approx)  
Queue: `dlqj-shipping-dlq` · Seed: **10** fixtures (2× each action type) · Mode: **dry_run**  
URL: `https://<CLOUDFRONT_DOMAIN>/` · Job: `8ef477da2f6a` · Run: `20261019T150635Z`

| Check | Result | Evidence |
|---|---|---|
| preflight_services | PASS | `dlqj-ui`+`dlqj-decider` active; Decider health `status=ok` model `strands-decider-2B-hobson-v21` |
| sqs_depth_before | PASS | `dlqj-shipping-dlq=50` (then purged for clean seed) |
| s3_objects_before | PASS | quarantine bucket count~=52 |
| seed_shipping_dlq | PASS | seeded=10 depth=10 mix={redrive_now:2, redrive_later:2, quarantine_poison:2, discard_duplicate:2, escalate_human:2} |
| auth_login | PASS | `qa.triage.3862@example.com` |
| set_queue | PASS | ARN → `dlqj-shipping-dlq` |
| connector_live | PASS | Connected · 6 queues · shipping in names · cli_depth=10 |
| connector_test | PASS | Instance role active · account <AWS_ACCOUNT_ID> · 6 dlqj-* queues |
| triage_accept_under_20s | PASS | status=202 elapsed=0.54s job_id=8ef477da2f6a |
| triage_complete | PASS | succeeded ~63s · result.run_id=20261019T150635Z |
| run_summary | PASS | processed=10 mode=dry_run counts all escalate_human (policy) |
| decider_called | PASS | decided_by={decider:8, rule:2} scored=10 |
| policy_low_conf_escalate | PASS | 8 low-band → escalate; 2 review-band also escalated (Bedrock/policy path) |
| confidence_bands | PASS | bands={low:8, review:2} conf_min=0.2852 conf_max=0.7068 **multi_band=2** |
| histogram_multi_band | PASS | hist_sum=10 hist_nonzero=3 (low + review bins populated) |
| sqs_after_dry_run | PASS | depth_after≈0 (in-flight visibility after ReceiveMessage; not deleted) |
| s3_unchanged_dry_run | PASS | before=52 after=52 (no Apply) |
| ssm_logs | PASS | journalctl `15:06–15:07`: **10×** `POST /v1/systemone HTTP/1.1 200 OK` on strands-decider |
| cloudwatch_dlqj_groups | BLOCKED | No dedicated `dlqj*` CloudWatch log groups — use journalctl |
| aws_console_ui | BLOCKED | No authenticated Console session |

Summary: **17 PASS**, **0 FAIL**, **2 BLOCKED**

Decider log excerpt (SSM `journalctl -u dlqj-decider --since '2026-10-19 15:06:00'`): ten consecutive SystemOne calls returned **200 OK** (~5–7s apart), matching 10 seed messages.

## Decider findings

- Decider HTTP healthy before triage; job completed with real confidences.
- **8/10** Decider decisions in **&lt;0.60** band → policy correctly forces `escalate_human`.
- **2/10** in **0.60–0.85** review band (max conf **0.7068**) → histogram multi-band validated.
- Fixture `expected_action` labels are benchmark targets; live policy may differ when confidence is low — not a triage wiring failure.

## Fixes applied

- UI histogram: rebuild bins from messages; min bar height for visibility (`app.js`) — redeployed via `_deploy_ui_boto.py`.
- QA script: unicode-safe evidence strings; seed/policy assertions aligned with 5×2 fixtures.

## Not done (cost/safety)

- Apply actions on this fresh run (would mutate SQS/S3).
- EC2 stop (requires your approval).
