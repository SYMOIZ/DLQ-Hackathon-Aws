# REQUIREMENTS.md — DLQ Judge

Document version: 1.1 · Date: 2026-10-18 · Owner: project author · Status: Draft (UI_SPEC 1.1 reconciliation)

All requirement IDs are stable. Tests in `TESTING_QA_UAT.md` reference them. UI requirements (`UI-xx`) live in `UI_SPEC.md`; this file references them where a functional requirement depends on the UI.

---

## 1. Problem and goal

Failed SQS messages accumulate in dead-letter queues. Triage today is manual: engineers read messages one by one, and bulk redrive replays "poison" messages that fail again. DLQ Judge decides a safe recovery action for every message, acts only when confident, explains failure clusters, and records every decision.

**Goal for v1.0:** a working, demonstrable, benchmarked hackathon entry that runs on one developer machine and one AWS account, using only synthetic data.

## 2. Users

| User | Need |
|---|---|
| Backend / platform engineer | Empty a DLQ safely; see why each message got its action |
| On-call engineer | Avoid re-flooding the DLQ with poison messages |
| Hackathon judge / article reader | See Decider 2B make a real, measurable decision |

## 3. Scope

**In scope (v1.0):** CLI, local web UI (5 screens in `UI_SPEC.md`), Strands agent mode with the reusable intervention pattern, Decider 2B decisions, Bedrock second opinions and cluster explanations, benchmark, CloudFormation stack deployed with AWS CLI, synthetic dataset.

**Out of scope (v1.0):** Lambda or scheduled runs; production or customer queues; FIFO queues; authentication or multi-user access; multi-account or multi-region; editing thresholds from the UI; starting a triage run from the UI; cluster-level bulk actions; mobile layout; fine-tuning Decider; any feature not in `UI_SPEC.md`.

## 4. Fixed decision definition

| Item | Value |
|---|---|
| Question type | Decider `choice` |
| Question text | `What is the safest next action for this failed message?` |
| Options (fixed order) | `redrive_now`, `redrive_later`, `quarantine_poison`, `discard_duplicate`, `escalate_human` |
| UI labels | Redrive now · Redrive later · Quarantine · Discard duplicate · Escalate to human |
| Confidence bands | `auto` ≥ 0.85 · `review` 0.60 to < 0.85 · `low` < 0.60 |
| Discard guard | Automatic `discard_duplicate` only if confidence ≥ 0.90 **and** idempotency key present |

## 5. Functional requirements

| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-01 | Read up to `DLQJ_BATCH_SIZE` (default 300) messages from the DLQ with all message attributes, using `ReceiveMessage` (max 10 per call, visibility timeout 300 s). In dry-run no message is deleted or moved. | After a dry run, `ApproximateNumberOfMessages` on the DLQ returns to its starting value within 300 s (TC-I05). |
| FR-02 | Build a state object per message (`ARCHITECTURE.md §5.2`). Mask emails → `[EMAIL]`, phone numbers → `[PHONE]`, runs of 13–19 digits → `[NUMBER]`. Truncate body to 2,000 characters with suffix `...[truncated]`. | TC-U01–U06 pass. No unmasked seeded email appears in logs, run files, API responses or Bedrock prompts (TC-S03). |
| FR-03 | Ask Decider one `choice` question with exactly the 5 options. Store choice, all 5 probabilities, confidence and latency. | TC-U15, TC-I02 pass; every decision record has 5 probabilities summing to 1 ± 0.01. |
| FR-04 | Apply confidence bands: `auto` → act; `review` → Bedrock second opinion, act only if Bedrock picks the same option, else escalate; `low` → escalate. | TC-U07–U10, TC-U16–U18 pass. |
| FR-05 | If both `error_type` and `error_text` are missing, escalate with reason `missing_evidence`, `decided_by = rule`, without calling Decider. | TC-U14 passes. |
| FR-06 | Discard guard (section 4). A failed guard escalates with reason `discard_guard`, `decided_by = rule`. | TC-U11–U13 pass. |
| FR-07 | Dry-run is the default for CLI, agent and UI. Actions run only through the apply flow in `SECURITY.md §4`. | TC-U24, TC-A07, TC-A08 pass. |
| FR-08 | Execute actions in apply mode (`ARCHITECTURE.md §5.6`). Every destructive action first writes a backup copy to S3 `backup/<run_id>/<message_id>.json`, then performs the action, then deletes from the DLQ only if the previous steps succeeded. | TC-U21, TC-I01 pass. |
| FR-09 | Group messages with final action `quarantine_poison` by `error_type`. One Bedrock call per cluster, max 5 sample messages. Output root cause, suggested fix, evidence IDs. Evidence IDs not in the samples are dropped and the claim is marked `unverified`. | TC-U20, TC-I04 pass. |
| FR-10 | Write per run: `runs/<run_id>/summary.json`, `decisions.jsonl`, `clusters.json` (contracts in `ARCHITECTURE.md §5`). | Files validate against the contracts (TC-U25). |
| FR-11 | Benchmark approaches A (rules), B (Bedrock only), C (DLQ Judge) on the labelled dataset; write `bench/results/results.json` and `results.md`. | TC-B01–B04 pass. |
| FR-12 | Cap Bedrock calls per run at `DLQJ_BEDROCK_MAX_CALLS` (default 50). When reached, further `review` messages escalate with reason `bedrock_cap`. | TC-U19 passes. |
| FR-13 | Local web UI served by Python standard library on `127.0.0.1:${DLQJ_UI_PORT}` implementing exactly the screens in `UI_SPEC.md` (S1–S5 + shared chrome; Settings vision out of scope — UI_SPEC §11). | All in-scope `UI-xx` acceptance checks pass (TC-UI01–UI30). |
| FR-14 | Human override: in a dry-run, a user can change the planned action of one message from the detail drawer, and revert to the model decision. The override is stored in `decisions.jsonl` and used when actions are applied. UI shows **Overridden** and a revert control (UI-16b). | TC-A05, TC-A06, TC-UI20, TC-UI25 pass. |
| FR-15 | Restore (rollback, CLI only): `dlq-judge restore --run <run_id> [--message <id>]` re-sends backed-up messages to the DLQ from S3. Dry-run by default; `--apply --yes` to execute. | TC-I07 passes. |
| FR-16 | Agent mode: a Strands agent with tools for each action; the `FailedMessageRecoveryGuard` intervention runs Decider + policy in `before_tool_call` and returns `Deny` when the tool does not match the verdict. | TC-U23, TC-I08 pass. |
| FR-17 | Queue allowlist: the tool refuses any queue name that does not start with `DLQJ_QUEUE_PREFIX` (default `dlqj-`). | TC-U26 passes. |
| FR-18 | Idempotency: a message with an applied action in a run is never acted on again in that run. | TC-U22 passes. |
| FR-19 | `dlq-judge doctor` checks env vars, AWS identity, stack outputs, Decider server, Bedrock model access. It makes no changes. | TC-I09 passes. |
| FR-20 | `dlq-judge seed` sends the synthetic dataset to the DLQ (directly, with attributes). Refuses if the DLQ is not empty unless `--force`. | TC-I06 passes. |
| FR-21 | `dlq-judge teardown` empties the bucket and deletes the stack after a typed confirmation. | TC-I10 passes. |

## 6. Non-functional requirements

| ID | Requirement | Target | Verified by |
|---|---|---|---|
| NFR-01 | Median Decider latency per message on the dev machine | ≤ 300 ms (record actual hardware) | TC-B05 |
| NFR-02 | Unsafe actions on the labelled set (poison redriven, non-duplicate discarded) | 0 | TC-B01 |
| NFR-03 | Runtime dependencies | `strands-agents`, `strands-decider`, `boto3` only | TC-Q03 |
| NFR-04 | Dev dependencies | `pytest`, `pytest-cov` only | TC-Q03 |
| NFR-05 | AWS spend for the whole project | < USD 10 (budget alert at USD 5) | AWS Budgets |
| NFR-06 | Unit test line coverage of `policy`, `state`, `masking`, `actions`, `engine` | ≥ 85% | TC-Q02 |
| NFR-07 | UI first render with 300 messages | ≤ 1 s on the dev machine after API responds | TC-UI19 |
| NFR-08 | UI supported browsers | Latest Chrome, Firefox, Safari on desktop; 1440 px reference width | UAT |
| NFR-09 | UI colour themes | Light and dark via sidebar toggle (OS as first-visit fallback) | TC-UI18 |
| NFR-10 | All network listeners bind to `127.0.0.1` only | — | TC-S05 |
| NFR-11 | Reproducibility | Two runs on the same seed give the same Decider choices | TC-Q04 |

## 7. Environment configuration

All configuration comes from environment variables (loaded by `config.py`; an optional `.env` file is read with a small stdlib parser, never committed).

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AWS_PROFILE` | yes | — | Profile that assumes role `dlqj-runner` |
| `DLQJ_REGION` | yes | `us-east-1` | AWS region for all services |
| `DLQJ_STACK_NAME` | no | `dlq-judge` | CloudFormation stack name |
| `DLQJ_QUEUE_PREFIX` | no | `dlqj-` | Allowlist prefix (FR-17) |
| `DLQJ_SOURCE_QUEUE` | no | `dlqj-orders` | Source queue name |
| `DLQJ_DLQ` | no | `dlqj-orders-dlq` | Dead-letter queue name |
| `DLQJ_BUCKET` | no | from stack output `QuarantineBucketName` | Backup and quarantine bucket |
| `DLQJ_BEDROCK_MODEL_ID` | yes | — (see OQ-03) | Bedrock model or inference-profile ID |
| `DLQJ_BEDROCK_MAX_CALLS` | no | `50` | FR-12 cap (second opinions) |
| `DLQJ_MAX_CLUSTERS` | no | `5` | Max clusters explained by Bedrock (FR-09) |
| `DLQJ_DECIDER_URL` | no | `http://127.0.0.1:8000` | Local Decider server |
| `DLQJ_DECIDER_MODEL` | no | `StrandsAgents/strands-decider-2B-hobson-v21` | Decider checkpoint |
| `DLQJ_DECIDER_TIMEOUT_S` | no | `5` | Per-request timeout |
| `DLQJ_AUTO_MIN` | no | `0.85` | Band threshold |
| `DLQJ_REVIEW_MIN` | no | `0.60` | Band threshold |
| `DLQJ_DISCARD_MIN` | no | `0.90` | Discard guard |
| `DLQJ_BATCH_SIZE` | no | `300` | Max messages per run |
| `DLQJ_REDRIVE_DELAY_S` | no | `300` | `redrive_later` delay (60–900) |
| `DLQJ_RUNS_DIR` | no | `./runs` | Run output folder (git-ignored) |
| `DLQJ_UI_PORT` | no | `8765` | Local UI port |

`config.py` validates types and ranges at start-up and exits with a clear message on any invalid value.

## 8. Assumptions

| ID | Assumption | Impact if wrong |
|---|---|---|
| A-01 | `UI_SPEC.md` matches the approved mockup at `design/mockup/` after P0-T7 reconciliation | UI phases rework if user rejects reconciled spec |
| A-02 | One AWS account, one region, admin access for setup | Deployment steps change |
| A-03 | Dev machine can run Decider 2B (GPU ≥ 6 GB VRAM or Apple Silicon, 16 GB RAM) | Latency targets and demo size change |
| A-04 | `strands-decider serve` exposes an HTTP endpoint (`/v1/systemone`) whose request/response schema is captured in the P0 spike | Client code changes; fallback is in-process load |
| A-05 | A small Bedrock text model with the Converse API is enabled in the region | Model choice or region changes |
| A-06 | Standard (not FIFO) SQS queues | FIFO needs group IDs and dedup IDs |
| A-07 | Error details are carried in message attributes `error_type`, `error_text`, `idempotency_key`, `original_receive_count` set by the producer (here: the seed command) | State builder needs another source |
| A-08 | The demo uses a single run at a time; the UI shows one run | Run selector needed (not in design) |

## 9. Open questions

Blocking questions must be answered before the phase named.

| ID | Question | Blocks | Provisional / resolved answer | Status |
|---|---|---|---|---|
| OQ-01 | Provide the approved UI mockup file | P5 (UI) | Placed at `design/mockup/DLQ Judge.dc.html` (+ support.js, standalone). UI_SPEC 1.1 reconciled | ANSWERED |
| OQ-02 | Hackathon submission deadline | Timeline | Plan for 13 working days; finish 2 days early | OPEN |
| OQ-03 | Region and Bedrock model ID | P4 | Region `us-east-1`. Model: P0-T5 list + converse 2 cheapest; final after P6 (D-003) | ANSWERED (region); model → P6 |
| OQ-04 | Dev hardware (GPU model or Mac chip) | P0 | AMD Ryzen 5 7430U + Radeon Graphics, 15 GB RAM; latency in P0-T3 | ANSWERED |
| OQ-05 | How does an overridden row look? | P5 | Mockup: status **Overridden** + revert link (UI-16b) | ANSWERED |
| OQ-06 | Apply confirmation dialog | P5 | Mockup: custom modal with per-action counts (UI-01e) | ANSWERED |
| OQ-07 | Loading, empty and error states | P5 | Accepted provisional plain text (UI-23 / §8); filtered empty string from mockup | ANSWERED |
| OQ-08 | Pagination for the message table | P5 | Mockup: 25 rows/page, Previous/Next (UI-10f) | ANSWERED |
| OQ-09 | Override to `discard_duplicate` below 0.90? | P4 | Allowed; warning shown; logged as human override | ANSWERED |
| OQ-10 | Which run does the UI show? | P5 | The run passed to `dlq-judge ui --run <id>`, default the latest | ANSWERED |
| OQ-11 | Exact Decider server schema | P2 | Captured in P0 spike into `tests/fixtures/decider_response.json` | OPEN |
| OQ-12 | GitHub repo owner/name | P8 | `dlq-judge` under the user's account | OPEN |
| OQ-13 | Benchmark screen before real results exist | P6 | Bundled sample with `Sample data · placeholder numbers` banner | ANSWERED |
| OQ-14 | UAT testers (who, how many) | P7 | 2 engineers not involved in the build | OPEN |
| OQ-15 | After a partly failed apply, may the user click Apply again? | P5 | Yes; idempotency (FR-18); mode stays `dry_run` until all actionable done | ANSWERED |
| OQ-16 | Navigation between screens | P5 | Mockup: left sidebar Workspace nav (UI-22); Settings deferred §11 | ANSWERED |
| OQ-17 | Build mockup Settings / multi-account / auth in v1.0? | P5 | No — out of scope (REQUIREMENTS §3); D-001 | ANSWERED |

## 10. Release criteria (v1.0)

Product
- [ ] FR-01 to FR-21 implemented, each covered by at least one passing test
- [ ] NFR-02: 0 unsafe actions (TC-B01)
- [ ] All in-scope `UI-xx` checks pass; `UI_SPEC.md` status `Approved`; reconciliation log complete; Settings vision remains out of scope (§11)
- [ ] Benchmark results for A, B, C in `bench/results/results.md`, with hardware and versions
- [ ] UAT-01 to UAT-04 passed by at least two testers
- [ ] Teardown leaves no `dlqj` resources (TC-I10)

Hackathon
- [ ] Decider 2B makes the action decision; Bedrock provides generation
- [ ] Public GitHub repo with `LICENSE` (Apache-2.0)
- [ ] Reusable pattern in `patterns/failed_message_recovery/` with question, options, hook wiring, usage note
- [ ] Builder Center article published
- [ ] Public demo video under 3 minutes
- [ ] Tags `#strands-decider-2b` and `#policy`
- [ ] Project not published before the hackathon

Security
- [ ] All `SECURITY.md §9` checklist items pass
- [ ] Secret scan clean; dependency audit clean or documented
