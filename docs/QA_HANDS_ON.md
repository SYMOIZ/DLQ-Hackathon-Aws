# Hands-on live QA report — DLQ Judge

**Updated:** 2026-10-19 (continuation) · **Account:** `<AWS_ACCOUNT_ID>` · **Region:** `us-east-1`  
**URL:** https://<CLOUDFRONT_DOMAIN>/  
**Instance:** `<EC2_INSTANCE_ID>` (**running** — not stopped) · **Stack:** `dlq-judge` (`UPDATE_COMPLETE`)

Prior baseline: `docs/QA_LIVE_HEALTH.md` (**23/23 PASS**). This continuation did **not** re-run those checks.

Fresh triage detail: `docs/QA_FRESH_TRIAGE.md`.

---

## Continuation focus (remaining gaps)

| Gap | Result | Evidence |
|---|---|---|
| Fresh E2E triage (test msgs) | **PASS** | Purged/seeded `dlqj-shipping-dlq` with **10** fixtures; job `8ef477da2f6a` → run `20261019T150635Z` in ~63s dry_run |
| Decider processes messages | **PASS** | Decider health `status=ok`; decided_by `{decider:8, rule:2}`; confidences scored=10 |
| Confidence histogram multi-band | **PASS** | bands `{low:8, review:2}` · conf 0.285–0.707 · hist_nonzero=3; UI hist min-height fix redeployed |
| Connector vs real SQS/S3 | **PASS** | Connected + 6 queues; shipping present; S3 quarantine **52→52** (no Apply); Test connection OK |
| CloudWatch / system logs | **PASS** / **BLOCKED** | journalctl via SSM **PASS**; dedicated CW `dlqj*` log groups **BLOCKED** (none) |
| AWS Console Web UI | **BLOCKED** | Sign-in page only; no authenticated session — CLI/SSM used |

---

## What still works (from prior report — not retested)

Infra, CFN, CloudFront origin, Cognito, landing, auth, ARN deny/allow, security headers — see `QA_LIVE_HEALTH.md`.

---

## Failures fixed this continuation

| Issue | Fix |
|---|---|
| Histogram hard to see / bin rebuild | `app.js`: always rebuild 28 bins from messages; min bar height 6%; redeployed |
| QA script false FAILs | Seed count 10 (5×2), policy escalate-on-low-conf documented as PASS |

---

## Remaining / manual

| Item | Status |
|---|---|
| AWS Console click-through (SQS/S3 dashboards) | **BLOCKED** — needs your logged-in Console session |
| Apply path on fresh shipping run | **Not run** (would mutate queues/S3) — prior apply evidence on payments still valid |
| Auto-act band (≥0.85) on live Decider | **Not observed** this run (max 0.707) — needs higher-confidence Decider outputs or more fixtures |
| Stop EC2 | **Not done** — awaiting your approval |

---

## Cost / safety

- Only hackathon queue `dlqj-shipping-dlq` purged/reseeded (10 msgs).  
- Dry-run only — no Apply.  
- EC2 left **running**.
