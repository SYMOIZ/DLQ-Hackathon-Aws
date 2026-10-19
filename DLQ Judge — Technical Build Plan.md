# DLQ Judge — Technical Build Plan

Oct 18, 2026 · @Syed

## Scope, goals and assumptions

One engineer builds a local Python CLI agent in 12 working days that triages a real SQS dead-letter queue (DLQ) with Strands Decider 2B, uses Amazon Bedrock for second opinions and explanations, and proves it with a reproducible benchmark.

**Goals**

1. Decide one of five recovery actions per failed message, with a confidence score.
2. Act automatically only when confident; otherwise ask Bedrock or escalate.
3. Never take an unsafe action on the labelled test set.
4. Publish a reusable decision pattern, benchmark results, article and demo video for the hackathon.

**Assumptions**

- One AWS account and one region (e.g. `us-east-1`); the engineer has admin access for setup.
- Development machine: Python 3.11+, 16 GB RAM; a GPU with 6 GB+ VRAM or an Apple Silicon Mac for Decider.
- All message data is synthetic. No production queues.
- Day 1 is the first working day after this plan is approved.

**Open question:** the hackathon submission deadline. Confirm it on the rules page and shift the timeline so Phase 7 ends at least 2 days before it.

## Prerequisites and AWS resources

Everything below must be in place before Phase 1 starts; setup takes about half a day.

**Accounts and access**

- [ ] AWS account with billing alerts enabled (AWS Budgets, monthly budget of USD 10 with email alert at 50%)
- [ ] IAM Identity Center or IAM user for development, using short-lived credentials (`aws sso login`)
- [ ] Bedrock model access enabled for one small text model in the chosen region (e.g. an Amazon Nova Lite/Micro or Claude Haiku model)
- [ ] AWS Builder Center profile, GitHub account, Hugging Face access for the Decider weights

**Local tools**

| Tool | Version | Purpose |
| --- | --- | --- |
| Python | 3.11+ | Runtime |
| AWS CLI | v2 | Credentials, manual checks |
| `strands-decider` | latest on PyPI | Runs Decider locally (`strands-decider serve`) |
| `strands-agents` | latest on PyPI | Agent loop and interventions |
| `boto3` | latest | SQS, S3, Bedrock, CloudWatch |
| `pytest` | latest | Tests (dev only) |
| `moto` | latest | AWS mocks for unit tests (dev only, optional) |

**AWS resources created by the project**

| Resource | Name | Notes |
| --- | --- | --- |
| SQS standard queue | `dlqj-orders` | Source queue; redrive target |
| SQS standard queue | `dlqj-orders-dlq` | DLQ; `maxReceiveCount` = 3 on the source queue's redrive policy |
| S3 bucket | `dlqj-quarantine-<account-id>` | SSE-S3, block public access, 7-day lifecycle expiry |
| IAM role | `dlqj-runner` | Least-privilege policy (Security section) |
| CloudWatch log group | `/dlq-judge/runs` | 7-day retention (optional) |
| CloudFormation stack | `dlq-judge` | Creates all of the above; deleting it removes them |

**Verify before coding**

- [ ] `strands-decider ask StrandsAgents/strands-decider-2B-hobson-v21 --state "test" --choice "Pick one?=a,b"` returns an answer
- [ ] `strands-decider serve ... --port 8000` starts and answers on `http://127.0.0.1:8000`
- [ ] `aws bedrock-runtime converse` works with the chosen model ID
- [ ] Read `examples/strands/` in the Decider repo for the exact request and response JSON of the server

## Architecture

A single local process owns every decision; AWS services only hold, move and explain messages, and nothing runs in AWS when the CLI is idle.

&#91;embedded content: architecture · 4 local components, 4 AWS services\]

**Request path for one batch**

1. Triage loop receives up to 10 messages per `ReceiveMessage` call from the DLQ (visibility timeout 300 s) until the batch size is reached.
2. State builder turns each message into masked state; missing evidence goes straight to escalate.
3. Decider returns choice, probabilities and confidence.
4. Policy applies bands and guards. Messages in the 0.60–0.85 band get a Bedrock second opinion.
5. Actions run in apply mode: send or put first, delete from the DLQ only on success.
6. Quarantined messages are grouped; Bedrock explains each group.
7. Run log and HTML report are written; run metrics are printed.

**Agent mode:** the same steps run as Strands tools, and the `FailedMessageRecoveryGuard` intervention checks every destructive tool call before it executes.

## Technical requirements

Each requirement has an ID that test cases and release criteria refer to.

**Functional**

| ID | Requirement |
| --- | --- |
| FR-01 | Read up to N messages (default 300) from the DLQ with attributes, without deleting them until an action completes |
| FR-02 | Build a state object per message; mask emails, phone numbers and card-like numbers; truncate body to 2,000 characters |
| FR-03 | Ask Decider one choice question with exactly 5 options; record all probabilities and confidence |
| FR-04 | Apply the confidence policy: ≥ 0.85 act; 0.60–0.85 Bedrock check; < 0.60 escalate |
| FR-05 | Escalate without calling Decider when error type and error text are both missing |
| FR-06 | Allow `discard_duplicate` only with confidence ≥ 0.90 and an idempotency key present |
| FR-07 | Dry-run by default; `--apply` executes actions |
| FR-08 | Execute actions: redrive (SendMessage to source, then DeleteMessage from DLQ), delayed redrive (DelaySeconds 60–900), quarantine (PutObject to S3, then delete), discard (delete), escalate (no change) |
| FR-09 | Group quarantined messages by error type; one Bedrock call per group (max 5 samples) |
| FR-10 | Write a JSONL decision log and a self-contained HTML report per run |
| FR-11 | Run the benchmark: rules, Bedrock-only, DLQ Judge on the labelled set |
| FR-12 | Cap Bedrock calls per run (default 50); stop calling and escalate when the cap is hit |

**Non-functional**

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-01 | Median Decider latency per message on the dev machine | ≤ 300 ms (measure; adjust if hardware differs) |
| NFR-02 | Unsafe actions on the labelled set | 0 |
| NFR-03 | Runtime dependencies beyond the standard library | `strands-agents`, `strands-decider`, `boto3` only |
| NFR-04 | Idempotent actions: re-running a run must not double-redrive | Checked by message ID in the run log |
| NFR-05 | AWS spend for the whole project | Under the USD 10 budget |
| NFR-06 | Unit test coverage of `policy`, `state`, `actions` | ≥ 85% lines |

## Repository structure

One public GitHub repo, Apache-2.0 licence, with the reusable pattern kept in its own folder so others can copy it alone.

```
dlq-judge/
├── LICENSE                      # Apache-2.0
├── README.md                    # quick start, demo GIF, benchmark table
├── pyproject.toml               # 3 runtime deps; dev extras: pytest, pytest-cov, moto
├── infra/
│   └── template.yaml            # CloudFormation: queues, bucket, role, log group
├── dlq_judge/
│   ├── __init__.py
│   ├── cli.py                   # argparse: seed, triage, bench, report, teardown
│   ├── config.py                # thresholds, caps, model IDs (env + defaults)
│   ├── sqs_io.py                # receive, send, delete, change visibility
│   ├── state.py                 # message -> state dict, PII masking
│   ├── decider_client.py        # HTTP client for local Decider server (urllib)
│   ├── policy.py                # confidence bands + safety rules
│   ├── bedrock_client.py        # Converse API: second opinion, cluster explain
│   ├── actions.py               # redrive, delay, quarantine, discard, escalate
│   ├── agent.py                 # Strands agent, tools, intervention wiring
│   ├── clusters.py              # group quarantined messages
│   ├── runlog.py                # JSONL log, idempotency checks
│   └── report.py                # HTML report (string templates, stdlib)
├── patterns/
│   └── failed_message_recovery/
│       ├── README.md            # how to reuse in 10 lines
│       ├── question.py          # typed question + 5 options
│       ├── policy.py            # thresholds, safety rules
│       └── hook.py              # InterventionHandler (before_tool_call)
├── bench/
│   ├── dataset/messages.jsonl   # 300 labelled synthetic messages
│   ├── generate.py              # deterministic generator (seeded)
│   ├── baseline_rules.py
│   ├── baseline_bedrock.py
│   └── run_bench.py             # writes results.json + results.md
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── docs/
    ├── architecture.md
    ├── article-draft.md
    └── demo-script.md
```

## Implementation details

The deterministic code (state, policy, actions) is plain Python; the agent and Bedrock only wrap it, so every safety rule is testable without models.

### 1. Message state (`state.py`)

```json
{
  "message_id": "b7c1...",
  "source_queue": "dlqj-orders",
  "receive_count": 4,
  "age_minutes": 37,
  "error_type": "ThrottlingException",
  "error_text": "Rate exceeded for table orders",
  "has_idempotency_key": true,
  "body_excerpt": "{\"order_id\": \"A-1042\", \"email\": \"[EMAIL]\"}"
}
```

- Error fields come from SQS message attributes `error_type` and `error_text`, which the producer (the seed script here) sets.
- Render the state as short labelled lines, not raw JSON, when sending to Decider: `Error type: ...`, `Error text: ...`, `Receive count: ...`.

### 2. Decision (`decider_client.py`, `patterns/.../question.py`)

- Question: `What is the safest next action for this failed message?`
- Options, in this order: `redrive_now`, `redrive_later`, `quarantine_poison`, `discard_duplicate`, `escalate_human`.
- Call the local server with `urllib.request` (no extra HTTP library). Copy the request and response schema from the repo's server example; store the parsed result as `{choice, confidence, probabilities}`.
- Timeout 5 s; on error or timeout, the decision becomes `escalate_human` with reason `decider_unavailable`.
- Confidence for a choice is derived as (N × p\_max − 1) / (N − 1), so 0.85 with 5 options means p\_max ≈ 0.88. Log both values.

### 3. Policy (`policy.py`)

```python
def decide(state, result, cfg) -> Verdict:
    if not state.error_type and not state.error_text:
        return Verdict("escalate_human", "missing_evidence")
    if result.choice == "discard_duplicate" and (
        result.confidence < cfg.discard_min or not state.has_idempotency_key):
        return Verdict("escalate_human", "discard_guard")
    if result.confidence >= cfg.auto_min:          # 0.85
        return Verdict(result.choice, "auto")
    if result.confidence >= cfg.review_min:        # 0.60
        return Verdict(result.choice, "needs_bedrock")
    return Verdict("escalate_human", "low_confidence")
```

### 4. Bedrock (`bedrock_client.py`)

- Use the Bedrock Runtime **Converse** API via boto3; temperature 0; max 300 output tokens.
- **Second opinion prompt:** give the state and the 5 options; require JSON `{"choice": ..., "reason": ...}`. If it agrees with Decider, act; if not, or JSON is invalid, escalate.
- **Cluster prompt:** up to 5 samples per error type; require JSON `{"root_cause", "suggested_fix", "evidence_message_ids"}`. Any ID not in the samples is dropped and the claim is marked `unverified`.
- Count calls; stop at the cap (FR-12).

### 5. Actions (`actions.py`)

| Action | SQS / S3 calls | Order rule |
| --- | --- | --- |
| `redrive_now` | SendMessage (source) → DeleteMessage (DLQ) | Delete only after send succeeds |
| `redrive_later` | SendMessage with DelaySeconds → DeleteMessage | Same |
| `quarantine_poison` | PutObject `quarantine/<run-id>/<msg-id>.json` → DeleteMessage | Same |
| `discard_duplicate` | DeleteMessage | Only after policy guard |
| `escalate_human` | ChangeMessageVisibility to 0 | Message stays in DLQ |

Before any action, check the run log: if the message ID already has a completed action, skip it (NFR-04).

### 6. Agent wiring (`agent.py`, `patterns/.../hook.py`)

- The Strands agent has tools: `list_dlq_batch`, `redrive`, `quarantine`, `discard`, `escalate`, `explain_clusters`, `write_report`. Its model is the Bedrock model.
- A `FailedMessageRecoveryGuard(InterventionHandler)` overrides `before_tool_call`. For `redrive`, `quarantine` and `discard` it runs Decider + policy and returns `Proceed` only if the verdict matches the tool; otherwise `Deny` with the reason.
- For batch speed, `triage` mode calls the policy loop directly and uses the agent only for clustering and the report. Both paths share the same policy code.

### 7. Report (`report.py`)

One self-contained HTML file (inline CSS, no JS libraries): run summary, counts per action, confidence histogram as inline SVG, message table, cluster cards, Bedrock call count.

## Development phases

Eight phases over 12 working days; each phase ends only when its acceptance criteria pass, and Phase 2 depends on the Day 1 spike succeeding.

&#91;embedded content: build timeline · 8 phases, 12 working days\]

### Phase 0 — Setup and spikes (Day 1)

**Depends on:** Prerequisites section.

1. Create repo, licence, `pyproject.toml`, CI that runs `pytest tests/unit`.
2. Run Decider CLI and server; record request/response JSON into `tests/fixtures/decider_response.json`.
3. Time 50 sample decisions; record median and p95.
4. Call Bedrock Converse once with the chosen model.
5. Check the hackathon gallery for similar projects.

**Deliverables:** repo skeleton, fixtures, `docs/spike-notes.md`. **Acceptance:** Decider answers locally; median latency recorded; Bedrock call succeeds.

### Phase 1 — Data and infrastructure (Day 2)

1. Write `infra/template.yaml`; deploy and delete once to prove teardown.
2. Write `bench/generate.py` (seeded) and produce the 300-message labelled dataset with holdout flags.
3. Write `dlq-judge seed`: sends messages to the source queue with attributes and forces them into the DLQ (receive without delete until `maxReceiveCount` is passed, or send directly to the DLQ for speed).

**Deliverables:** template, dataset, seed command. **Acceptance:** 300 messages visible in the DLQ with correct attributes; teardown leaves nothing.

### Phase 2 — Decision core (Days 3–4)

1. `state.py` with masking and truncation.
2. `decider_client.py` with timeout and error fallback.
3. `policy.py` exactly as in Implementation details.
4. `dlq-judge triage` dry-run: prints a decision per message and writes the JSONL log.
5. Quick offline accuracy check on the non-holdout slice; adjust question and state wording if accuracy is poor.

**Deliverables:** dry-run triage end to end. **Acceptance:** unit tests TC-U01 to TC-U15 pass; 300 decisions logged; no crash on malformed messages.

### Phase 3 — Actions and run log (Day 5)

1. `actions.py` with delete-after-success ordering.
2. `runlog.py` idempotency check.
3. `--apply` with confirmation.

**Deliverables:** working apply mode. **Acceptance:** integration test TC-I01 passes; re-running the same run ID performs no second action.

### Phase 4 — Bedrock, agent and hook (Days 6–7)

1. `bedrock_client.py`: second opinion, cluster explanation, call cap.
2. `clusters.py` grouping.
3. `patterns/failed_message_recovery/hook.py` (InterventionHandler) and `agent.py` with tools.
4. Pattern README with a 10-line usage example.

**Deliverables:** full triage with Bedrock; agent mode guarded by the hook. **Acceptance:** TC-U16 to TC-U22 and TC-I02 to TC-I04 pass; the hook denies a `discard` tool call that policy rejects.

### Phase 5 — Report and benchmark (Days 8–9)

1. `report.py` HTML report.
2. Baselines A and B; `run_bench.py` producing `results.json` and `results.md`.
3. Run benchmark 3 times; tune thresholds on the non-holdout slice only.

**Deliverables:** report, benchmark results. **Acceptance:** results reproduce within ±2 accuracy points across runs; 0 unsafe actions for C.

### Phase 6 — QA, security and UAT (Day 10)

1. Run all QA gates and the Security checklist.
2. Run UAT with 2–3 testers; fix blockers.

**Deliverables:** QA sign-off notes, UAT issues closed or listed. **Acceptance:** all QA gates pass; UAT-1 to UAT-3 pass.

### Phase 7 — Release and submission (Days 11–12)

1. Record demo (under 3 minutes) following `docs/demo-script.md`.
2. Write and publish the Builder Center article with both tags.
3. Tag `v1.0.0`; make repo public; submit.
4. Tear down AWS resources after recording.

**Deliverables:** video, article, release, submission. **Acceptance:** every Release criteria box ticked.

## Testing and QA

Three layers: unit tests with no network, integration tests against real AWS in a throwaway stack, and QA gates that block each phase from closing. The full test-case list is in the **Test cases** tab.

**Unit tests** (`tests/unit`, run on every commit, < 30 s)

- `state`: masking, truncation, missing attributes, unicode bodies
- `policy`: every band boundary (0.599, 0.60, 0.849, 0.85, 0.899, 0.90), discard guard, missing evidence
- `actions`: call order with mocked boto3 (stubbed client or `moto`); delete never called when send fails
- `decider_client`: parses a recorded server response; timeout → `escalate_human`
- `bedrock_client`: valid JSON, invalid JSON, disagreeing choice, unknown evidence IDs, call cap
- `runlog`: idempotency skip on re-run

**Integration tests** (`tests/integration`, run manually, marked `@pytest.mark.aws`)

- Deploy the stack, seed 30 messages, run `triage --apply`, assert queue and bucket contents match the decisions log, then tear down.
- Decider live test: 20 fixture states with clear answers return the expected choice.
- Bedrock live test: one second opinion and one cluster explanation return valid JSON.

**QA gates**

| Gate | Pass condition |
| --- | --- |
| Code | All unit tests pass; coverage ≥ 85% on `policy`, `state`, `actions` |
| Safety | 0 unsafe actions on the 300-message set |
| Repeatability | Two runs on the same seed give the same Decider choices; confidences may differ only in the 3rd decimal (Bedrock output is not compared) |
| Clean account | After teardown, `aws sqs list-queues --queue-name-prefix dlqj` and the bucket list return nothing |

Full list with inputs and expected results: Test cases

## Benchmarking

The benchmark runs offline from `bench/dataset/messages.jsonl` (no SQS needed), so anyone can reproduce it with one command: `python -m bench.run_bench --seed 42`.

**Dataset (300 messages, generator seed 42)**

| Failure type | Count | Correct label |
| --- | --- | --- |
| Transient timeout, recovered | 60 | `redrive_now` |
| Throttling / downstream outage | 50 | `redrive_later` |
| Schema error, bad payload | 60 | `quarantine_poison` |
| Missing required field | 40 | `quarantine_poison` |
| Duplicate with idempotency key | 40 | `discard_duplicate` |
| Ambiguous or unknown error | 50 | `escalate_human` |

60 messages (20%) use error wording held out from rule and prompt writing (the `holdout` flag in the file).

**Approaches**

- **A. Rules:** a dictionary of error-type and regex patterns mapped to actions, written before any results are seen.
- **B. Bedrock only:** the second-opinion prompt for every message.
- **C. DLQ Judge:** Decider + policy + Bedrock for the 0.60–0.85 band.

**Metrics (written to `results.json` and `results.md`)**

- Accuracy overall, per failure type, and on the holdout slice
- Unsafe-action count (poison redriven, non-duplicate discarded)
- Escalation rate
- Decision latency per message: median and p95
- Bedrock calls, input and output tokens, estimated cost using the current Bedrock price for the chosen model
- Calibration: accuracy per confidence band for C

**Rules for honest results**

- Run each approach 3 times; report the median.
- Record hardware, model versions and region in `results.md`.
- Publish the losing numbers too; do not tune thresholds on the holdout slice.

## UAT

Two or three engineers who did not build the tool follow only the README, on their own machine and AWS account, in one 60-minute session.

| # | Scenario | Pass condition |
| --- | --- | --- |
| UAT-1 | Install, deploy stack, seed queue | Done in ≤ 20 minutes without help |
| UAT-2 | Run `triage` (dry run) | Report opens; tester can say why 3 chosen messages got their action |
| UAT-3 | Run `triage --apply` | Queue and bucket state match the report |
| UAT-4 | Override one escalated message by hand | Clear how to do it from the report |
| UAT-5 | Reuse the pattern in a 20-line sample agent | Works using only the pattern README |
| UAT-6 | Run benchmark and teardown | Results reproduce within ±2 accuracy points; account is clean |

Collect feedback in a GitHub issue per tester. Any blocker in UAT-1 to UAT-3 must be fixed before release; others go to a known-issues list.

## Security

The tool can delete messages, so least privilege, dry-run defaults and masking are mandatory, not optional hardening.

**IAM policy for `dlqj-runner`** (resource-scoped, no wildcards on resources)

| Service | Actions | Resource |
| --- | --- | --- |
| SQS | `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`, `GetQueueAttributes` | DLQ ARN only |
| SQS | `SendMessage`, `GetQueueAttributes` | Source queue ARN only |
| S3 | `PutObject` | `arn:aws:s3:::dlqj-quarantine-<id>/quarantine/*` |
| Bedrock | `InvokeModel` (used by Converse) | The one chosen model or inference-profile ARN |
| CloudWatch Logs | `CreateLogStream`, `PutLogEvents` | `/dlq-judge/runs` log group only |

Optional: `cloudwatch:PutMetricData` on `*` with condition `cloudwatch:namespace = DLQJudge` (the action has no resource-level scoping), only if metrics are enabled. The role's trust policy allows only your own account's SSO role to assume it.

**Controls**

- [ ] Short-lived credentials only; no access keys in code, `.env` files or the repo
- [ ] Dry-run default; `--apply` prints a summary and needs `--yes` or an interactive confirm
- [ ] PII masking before any data leaves the process (Decider prompt, Bedrock prompt, logs, report)
- [ ] Message bodies sent to Bedrock are capped at 2,000 characters and are synthetic in all demos
- [ ] Prompt-injection guard: message text is passed as data inside clear delimiters; Bedrock output can only pick from the 5 options and never triggers an action alone
- [ ] S3 bucket: block public access, SSE-S3 encryption, 7-day expiry, TLS-only bucket policy
- [ ] Decider server binds to `127.0.0.1` only
- [ ] Dependency check: `pip-audit` (dev only) before release; pin versions in `pyproject.toml`
- [ ] Secret scan of the repo before making it public (e.g. GitHub secret scanning)

## Deployment and teardown

Deployment is one CloudFormation stack plus a local Python install; teardown is one command that leaves the account empty.

**Deploy**

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -e .            # strands-agents, strands-decider, boto3

# 2. AWS resources
aws cloudformation deploy --template-file infra/template.yaml \
  --stack-name dlq-judge --capabilities CAPABILITY_NAMED_IAM

# 3. Decider (separate terminal)
strands-decider serve StrandsAgents/strands-decider-2B-hobson-v21 --port 8000

# 4. Configure
export AWS_PROFILE=dlqj   # profile with role_arn = dlqj-runner, source_profile = your SSO profile
export DLQJ_REGION=us-east-1
export DLQJ_BEDROCK_MODEL_ID=<model or inference-profile id>

# 5. Run
dlq-judge seed --count 300 --seed 42
dlq-judge triage --queue dlqj-orders-dlq            # dry run
dlq-judge triage --queue dlqj-orders-dlq --apply --yes
```

**Teardown**

```bash
dlq-judge teardown   # empties the bucket, then deletes the stack
```

**Template contents (`infra/template.yaml`):** two SQS queues with a redrive policy (`maxReceiveCount` 3, DLQ retention 14 days), the S3 bucket with lifecycle and bucket policy, the `dlqj-runner` role, the log group with 7-day retention. Outputs: queue URLs, bucket name, role ARN.

**Release packaging:** tag `v1.0.0` on GitHub, attach `results.md` and a sample `report.html` to the release.

## Monitoring and logging

Every run is fully reconstructable from its JSONL log; CloudWatch is optional and used only for run-level metrics.

**Per-decision log line (`runs/<run-id>/decisions.jsonl`)**

```json
{"run_id":"2026-10-20T10-03","message_id":"b7c1...","choice":"redrive_later",
 "confidence":0.91,"probabilities":{"redrive_now":0.04,"redrive_later":0.93,...},
 "verdict":"auto","bedrock":null,"action":"redrive_later","status":"done",
 "decider_ms":142,"ts":"2026-10-20T10:03:11Z"}
```

**Run-level metrics** (printed at the end; optionally sent with CloudWatch `PutMetricData`, namespace `DLQJudge`)

| Metric | Use |
| --- | --- |
| `MessagesProcessed` | Throughput |
| `ActionCount` by action | Behaviour drift between runs |
| `EscalationRate` | Too high = thresholds or question need work |
| `BedrockCalls` | Cost control |
| `DeciderLatencyP50`, `P95` | Performance |
| `ActionErrors` | Failed SQS/S3 calls |

**Alerts:** AWS Budgets alert at USD 5; no other alarms for the MVP. CloudWatch custom metrics are billed per metric, so leave `--metrics` off unless needed.

## Risks

The biggest risks are model accuracy on unseen wording and running out of time before the demo; both have a fallback that keeps the submission valid.

| Risk | Likelihood | Impact | Mitigation | Fallback |
| --- | --- | --- | --- | --- |
| Decider accuracy too low on holdout | Medium | High | Reword question, add clearer state labels, tune thresholds on the non-holdout slice | Raise auto threshold; more goes to Bedrock; report honestly |
| Decider ignores question wording | Medium | Medium | Positive phrasing only; options named as clear verbs | Same as above |
| Decider too slow on dev hardware | Low | Medium | Measure on Day 1 | Smaller batch (100) for the demo |
| Server API differs from assumptions | Medium | Low | Copy schema from repo example on Day 1 | Load model in-process via `StrandsDeciderModel.load` |
| Bedrock model access not approved in region | Low | High | Request access during setup | Switch to another enabled small model or region |
| Wrong action deletes data | Low | High | Dry run default, delete-after-success, discard guard | Quarantine bucket keeps copies for 7 days |
| Similar project already in gallery | Medium | Medium | Check gallery before Phase 1 | Lead with benchmark + reusable pattern |
| Schedule slip | Medium | High | Phases 5–7 kept small | Drop CloudWatch metrics and cluster cards; keep the agent, hook and triage CLI |
| Cost overrun | Low | Low | Bedrock call cap, budget alert, teardown | — |

## Release criteria

Release `v1.0.0` and submit only when every box below is ticked.

**Product**

- [ ] FR-01 to FR-12 implemented and covered by at least one passing test
- [ ] 0 unsafe actions on the 300-message benchmark (NFR-02)
- [ ] Benchmark results for A, B and C published in `results.md`, with hardware and versions
- [ ] UAT-1 to UAT-3 passed by at least two testers
- [ ] Teardown leaves no `dlqj` resources

**Hackathon requirements**

- [ ] Agent uses Decider 2B for the action decision and Bedrock for generation
- [ ] Public GitHub repo, Apache-2.0 `LICENSE` file present
- [ ] Reusable pattern in `patterns/failed_message_recovery/` with question, options, hook wiring and usage note
- [ ] Builder Center article published, explaining the decision and what was learned
- [ ] Public demo video under 3 minutes showing the decision working
- [ ] Tags: `#strands-decider-2b` and `#policy`
- [ ] Project not published anywhere before this hackathon

**Security**

- [ ] Secret scan clean; `pip-audit` clean or findings documented
- [ ] IAM policy matches the Security table

## Sources

- [Agent Experience Hackathon: Strands Decider (rules)](https://builder.aws.com/build/hackathons/4f50957c-1d08-37ab-b11c-97516b9adeb4/agent-experience-hackathon?tab=rules)
- [strands-decider on PyPI](https://pypi.org/project/strands-decider/)
- [Strands Decider README (GitHub)](https://raw.githubusercontent.com/strands-labs/strands-decider/main/README.md)
- [strands-decider-2B-hobson-v21 model card](https://huggingface.co/StrandsAgents/strands-decider-2B-hobson-v21)
- [Strands Agents: Interventions](https://strandsagents.com/docs/user-guide/sdk/agents/interventions/)
- [Strands Python API: InterventionHandler](https://strandsagents.com/docs/api/python/strands.interventions.handler/)
- [Confidence formula for choice questions (buridan-2b card)](https://huggingface.co/jgalego/buridan-2b)

AWS service limits and prices (SQS DelaySeconds max 900 s, Bedrock and CloudWatch pricing) should be re-checked in the AWS documentation and pricing pages during setup.
