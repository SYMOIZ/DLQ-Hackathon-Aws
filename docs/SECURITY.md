# SECURITY.md — DLQ Judge

Document version: 1.1 · Date: 2026-10-18 · Status: Draft (UI apply modal ref updated)

Security controls in this file override any lower-ranked document and the UI on safety matters (`CURSOR_CONTEXT.md §2`). If a control needs UI not in the design, it is logged as a design gap, not built silently.

---

## 1. Threat summary

| Threat | Example | Control (section) |
|---|---|---|
| Accidental destructive action | Messages deleted or replayed by mistake | Dry-run default, apply flow, backups, restore (§4) |
| Wrong queue | Tool pointed at a real production DLQ | Queue allowlist, dedicated stack, role scope (§2, §4) |
| Credential leak | Keys committed to Git | Short-lived SSO credentials, no keys in files (§3) |
| Sensitive data exposure | PII in prompts, logs or UI | Synthetic data, masking, truncation (§5) |
| Local web attacks | Another site calls the local API (CSRF, DNS rebinding); XSS from message bodies | Loopback bind, token, Host/Origin checks, CSP, no `innerHTML` (§6) |
| Prompt injection | Message body says "discard everything" | Data delimiters; Bedrock can only confirm/block (§7) |
| Supply chain | Malicious or vulnerable package | 3 runtime deps, pinned versions, audit (§8) |

## 2. IAM

Two identities:

| Identity | Used for | Permissions |
|---|---|---|
| Your SSO admin/developer profile | `aws cloudformation deploy`, budget creation, teardown | Existing account permissions |
| Role `dlqj-runner` (created by the stack) | Everything the `dlq-judge` CLI and UI do | Least privilege below |

**`dlqj-runner` policy** (defined in `infra/template.yaml`; ARNs come from stack resources):

| Sid | Actions | Resource |
|---|---|---|
| `DlqAccess` | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes`, `sqs:GetQueueUrl`, `sqs:SendMessage` (seed, restore) | DLQ ARN |
| `SourceSend` | `sqs:SendMessage`, `sqs:GetQueueAttributes`, `sqs:GetQueueUrl` | Source queue ARN |
| `BucketWrite` | `s3:PutObject` | `arn:aws:s3:::<bucket>/backup/*`, `arn:aws:s3:::<bucket>/quarantine/*` |
| `BucketRestore` | `s3:GetObject` | `arn:aws:s3:::<bucket>/backup/*` |
| `BucketList` | `s3:ListBucket` with condition `s3:prefix` = `backup/*` | Bucket ARN |
| `Bedrock` | `bedrock:InvokeModel` | The one model ARN (and inference-profile ARN if a profile ID is used), passed as stack parameter `BedrockModelArn` |
| `StackRead` | `cloudformation:DescribeStacks` | The `dlq-judge` stack ARN |

No `sqs:DeleteMessage` on the source queue, no `s3:DeleteObject` (teardown uses the admin profile), no wildcards on resources.

**Trust policy:** principal = `arn:aws:iam::<account-id>:root` (any identity in your own account that is allowed `sts:AssumeRole` on this role). `MaxSessionDuration` 3600 s.

**Local profile** (`~/.aws/config`, never committed):

```ini
[profile dlqj]
role_arn = arn:aws:iam::<account-id>:role/dlqj-runner
source_profile = <your-sso-profile>
region = us-east-1
```

## 3. Credentials and secrets

- [ ] Only short-lived credentials (`aws sso login`); no IAM user access keys.
- [ ] No credentials, account IDs, ARNs with account IDs, or tokens in the repo. `.env` is git-ignored; `.env.example` has placeholders only.
- [ ] The UI token is generated per server start and never written to disk.
- [ ] Enable GitHub secret scanning and push protection before the repo goes public.

## 4. Destructive operation controls (the apply flow)

"Destructive" = `SendMessage`, `DeleteMessage`, `ChangeMessageVisibility` on the DLQ or source queue in a run, and S3 writes during apply or restore.

1. **Dry-run default.** `triage`, `agent`, `restore` and the UI make no destructive call unless the apply flow is completed.
2. **CLI apply:** requires `--apply` **and** either `--yes` or the user typing `APPLY` at an interactive prompt that shows queue name and action counts. Non-interactive without `--yes` → abort (exit 1).
3. **UI apply** requires all of:
   - server started with `dlq-judge ui --allow-apply` (otherwise the endpoint returns 403);
   - valid `X-DLQJ-Token`, `Host` and `Origin` (§6);
   - the user confirms the custom Apply modal (UI_SPEC UI-01e; OQ-06 answered);
   - body `{"confirm":"APPLY","expected_actionable_count":n}` where `n` matches the server's current count (prevents stale or replayed requests).
4. **Queue allowlist:** every SQS call goes through `aws_io.py`, which rejects queue names not starting with `DLQJ_QUEUE_PREFIX` (FR-17).
5. **Backup before change:** every destructive action first writes `backup/<run>/<id>.json` (FR-08). If the backup fails, the action does not run.
6. **Delete last:** DLQ delete happens only after the send/put succeeds.
7. **Discard guard:** automatic discard needs confidence ≥ 0.90 and an idempotency key (FR-06). Human overrides to discard are allowed with a visible warning (OQ-09) and are logged.
8. **Idempotency:** a message already `applied` in a run is never acted on again (FR-18).
9. **Rollback:** `dlq-judge restore` (FR-15). Backups expire after 7 days (bucket lifecycle).

### If something was applied by mistake

1. Stop the UI server (Ctrl+C).
2. `dlq-judge restore --run <run_id>` (dry run) → check the list.
3. `dlq-judge restore --run <run_id> --apply --yes`.
4. Messages redriven to the source queue may already have been consumed; this tool has no consumer, so in this project they remain in the source queue and can be inspected with `aws sqs receive-message`.

## 5. Data protection

- **Synthetic data only** (`bench/generate.py`); emails use `example.com`, names are invented, card-like numbers are random and fail the Luhn check.
- **Masking** (`masking.py`) before any data reaches Decider, Bedrock, logs, run files or the UI API: emails, phone numbers, 13–19 digit runs. The original body exists only in SQS and in the S3 backup.
- **Truncation:** state body ≤ 2,000 characters; log excerpts ≤ 200.
- **S3 bucket:** Block Public Access (all four settings), default encryption SSE-S3, bucket policy denying `aws:SecureTransport = false`, lifecycle expiry 7 days for `backup/` and `quarantine/`, versioning off.
- **SQS:** SSE-SQS enabled on both queues (`SqsManagedSseEnabled: true`).
- **Local files:** `runs/` is git-ignored. Run files contain masked data only.

## 6. Local network surface

| Control | Detail |
|---|---|
| Loopback only | UI server binds `127.0.0.1`. Decider server: check its bind address in P0; if it listens on all interfaces, use its host option to bind `127.0.0.1`, or document the OS firewall rule. TC-S05 verifies |
| Token | `X-DLQJ-Token` on every `/api/*` call (ARCHITECTURE §7) |
| DNS rebinding | Reject requests whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>` |
| CSRF | Reject `Origin` not matching the host; require JSON content type; no CORS headers are ever sent |
| Headers on every response | `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'` · `X-Content-Type-Options: nosniff` · `Referrer-Policy: no-referrer` · `Cache-Control: no-store` for `/api/*` |
| XSS | `app.js` sets message-derived text only with `textContent` or `createTextNode`; never `innerHTML`, `eval` or inline handlers. The token is placed in a `<meta>` tag, not in inline script |
| Body size | POST bodies > 4 KB → 400 |

## 7. Prompt injection

- Message content is wrapped in `<message>` / `<messages>` tags and the system prompt says it is data (ARCHITECTURE §9).
- Bedrock output must parse to the fixed JSON schema and the `choice` must be one of the 5 options; anything else → escalate.
- Bedrock can only confirm or block Decider's choice; it never chooses an action on its own and never calls tools.
- In agent mode, the guard re-checks every destructive tool call against Decider + policy, whatever the agent's reasoning says.
- TC-S04 seeds an injection message and checks that it is not discarded.

## 8. Dependencies and supply chain

- Runtime: `strands-agents`, `strands-decider`, `boto3`. Dev: `pytest`, `pytest-cov`. No others (NFR-03/04).
- Pin exact versions in `pyproject.toml` after the P0 spike; record them in `docs/DECISIONS.md`.
- Before release: run a vulnerability audit with a tool that is **not** added to the project (e.g. `pipx run pip-audit`); document findings.
- Decider weights: download only from the `StrandsAgents` organisation on Hugging Face; record the model revision hash in `docs/DECISIONS.md`.
- Frontend: no third-party JS or CSS, no CDN, no web fonts.

## 9. Security checklist (release gate)

| # | Check | Test |
|---|---|---|
| 1 | Runner role cannot delete from the source queue | TC-S01 |
| 2 | Runner role cannot read other S3 buckets | TC-S02 |
| 3 | No seeded email appears unmasked in run files, API responses, logs, captured Bedrock prompts | TC-S03 |
| 4 | Injection message not discarded | TC-S04 |
| 5 | UI and Decider not reachable from another host | TC-S05 |
| 6 | Secret scan clean | TC-S06 |
| 7 | API rejects missing/invalid token, bad Host, foreign Origin | TC-S07 |
| 8 | Apply endpoint returns 403 without `--allow-apply` | TC-A08 |
| 9 | Security headers present on every response | TC-S08 |
| 10 | Non-`dlqj-` queue names refused | TC-U26 |
| 11 | Dependency audit clean or documented | TC-Q03 |
| 12 | S3 bucket: public access blocked, encryption on, TLS-only policy | TC-S09 |
