# DLQ Judge — Product Concept

Oct 18, 2026 · @Syed

## Concept summary

DLQ Judge is a CLI agent that decides what to do with every failed message in an Amazon SQS dead-letter queue (DLQ), acts on confident decisions, and asks Amazon Bedrock only when it is unsure or needs to explain a failure pattern.

- **One-line pitch:** a fast, local decision model sorts hundreds of failed messages in seconds; a large model is called only for the hard cases.
- **Core idea:** Strands Decider 2B makes the repeated, closed-option decision per message. Bedrock writes the human-readable diagnosis per failure cluster.
- **What makes it different:** it acts on infrastructure state (queues and message attributes), not on chat, code or alerts. Every action is recorded with its confidence, so the result is auditable and benchmarkable.
- **Hackathon tags:** `#strands-decider-2b` `#policy`

## Problem and users

DLQs fill up silently, and clearing them is manual, repetitive and risky: redriving a bad message fails again, and deleting a good one loses data.

| User | Pain today | Job DLQ Judge does |
| --- | --- | --- |
| Backend / platform engineer | Reads messages one by one to decide redrive or delete | Sorts the whole DLQ and acts on the safe cases |
| On-call engineer | Bulk redrive replays poison messages and re-floods the DLQ | Holds back poison messages and redrives only transient failures |
| Team lead | No record of why messages were dropped | Gives an audit log of every action with its confidence |

**Main job to be done:** "Empty my DLQ safely, and tell me what is actually broken."

## Core experience and workflow

The user runs one command, `dlq-judge triage --queue orders-dlq`, and gets every message sorted, safe actions applied, and a report in under a minute for a few hundred messages.

&#91;embedded content: triage flow · 1 decision, 3 confidence bands\]

Quarantined messages are grouped by error type before Bedrock explains them, so one Bedrock call covers a whole cluster.

## Decision design

One typed **choice** question per message decides its action; a confidence threshold decides whether DLQ Judge acts alone or asks Bedrock.

**State sent to Decider** (compact JSON, no secrets): message body (truncated, PII-masked), error type and error text from message attributes, `ApproximateReceiveCount`, source queue name, age, and whether an idempotency key exists.

**Question:** "What is the safest next action for this failed message?" Phrased positively, because the model can miss inverted wording.

| Option | Meaning | Action taken |
| --- | --- | --- |
| `redrive_now` | Transient failure that is already over | Send back to the source queue |
| `redrive_later` | Throttling or downstream outage | Send back with a delay |
| `quarantine_poison` | Bad payload or schema; will always fail | Move to S3 quarantine |
| `discard_duplicate` | Already processed | Delete from the DLQ |
| `escalate_human` | Unclear or high-risk | Leave in the DLQ and flag in the report |

**Confidence policy**

| Confidence | Behaviour |
| --- | --- |
| ≥ 0.85 | Act automatically |
| 0.60–0.85 | Ask Bedrock for a second opinion; act only if both agree |
| < 0.60 | `escalate_human` |
| Missing error attributes | `escalate_human`, Decider not called |

**Safety rules (deterministic, always on):**

- `discard_duplicate` requires confidence ≥ 0.90 and an idempotency key.
- Dry-run is the default; actions need a `--apply` flag.
- Every decision is logged with its option probabilities.

## Bedrock role and explanations

Bedrock does the work Decider cannot: it writes text, and it is called per cluster or per uncertain message, never per routine message.

- **Second opinion:** for messages with confidence 0.60–0.85, Bedrock picks one of the same five options and gives a one-line reason.
- **Cluster diagnosis:** messages marked `quarantine_poison` are grouped by error type. Bedrock receives a few sample messages per group and returns a likely root cause and a suggested fix.
- **Run report:** a short summary for the team: what was redriven, quarantined, discarded and escalated, and why.

**Evidence rule:** every explanation must cite the message IDs and error fields it used. Claims without evidence are labelled "unverified". Bedrock never triggers an action on its own; it can only confirm or block Decider's choice.

## Architecture and dependencies

The agent and Decider run on the developer's machine; SQS, S3 and Bedrock are the only AWS services, all in one account and region, with no always-on compute.

&#91;embedded content: architecture · local machine + one AWS account\]

| Dependency | Status | Purpose |
| --- | --- | --- |
| `strands-agents` | Required | Agent loop and InterventionHandler hook |
| `strands-decider` | Required | Serves Decider 2B locally |
| `boto3` | Required | SQS, S3 and Bedrock calls |
| Amazon SQS (2 queues) | Required | Source queue and its DLQ |
| Amazon Bedrock (one small model) | Required | Second opinions and explanations |
| Amazon S3 (1 bucket) | Optional | Quarantine store; a local folder works for dry runs |
| Python standard library | Required | JSON, HTML report, CLI arguments |
| Lambda, NAT, databases, third-party APIs | Not used | — |

**Cost control:** no idle resources; a teardown script deletes the queues and bucket; Bedrock calls are capped per run. Confirm current SQS, S3 and Bedrock prices on the AWS pricing pages before quoting a figure.

## MVP scope

The MVP is a local Python CLI against one real SQS queue pair, seeded with synthetic messages, producing a static HTML report.

**In scope**

- [ ] Seed script: 300 labelled synthetic messages across 6 failure types (timeout, throttling, schema error, missing field, duplicate, unknown)
- [ ] Triage command: read DLQ, build state, ask Decider, apply confidence policy
- [ ] Actions: redrive, delayed redrive, quarantine to S3, delete, escalate (dry-run by default)
- [ ] Bedrock second opinion and cluster diagnosis
- [ ] HTML report: counts per action, confidence per message, cluster explanations
- [ ] Benchmark command against two baselines
- [ ] Teardown script that deletes all created resources

**Out of scope for MVP**

- Lambda or scheduled runs (local CLI only)
- Real production queues or customer data
- Web UI, authentication, multi-account support
- Fine-tuning Decider

## Benchmark design

All three approaches run on the same 300 labelled messages; results are published as measured, including where DLQ Judge loses.

| Approach | How it decides |
| --- | --- |
| A. Rules | Regex and error-code mapping to the 5 options |
| B. Bedrock only | Bedrock picks an option for every message |
| C. DLQ Judge | Decider for all, Bedrock only for 0.60–0.85 confidence |

**Metrics**

- Accuracy against labels, overall and per failure type
- Unsafe-action rate: a poison message redriven, or a valid message discarded
- Median and p95 decision latency per message
- Bedrock calls and estimated cost per 1,000 messages
- Calibration: accuracy within each confidence band

**Fairness rule:** rules are written before seeing results, and 20% of messages use error wording not seen while writing rules or prompts.

## Reusable decision pattern

The reusable asset is a "Failed-Message Recovery" pattern: one question, five options, a three-band confidence policy, and a hook that sits before any destructive queue action.

**What ships in the repo (`patterns/failed_message_recovery/`)**

- `question.py`: the typed question and option set
- `state.py`: builds the state from any message plus error metadata (works for SQS, EventBridge, Kinesis or Step Functions failures)
- `policy.py`: thresholds and safety rules, configurable
- `hook.py`: a Strands InterventionHandler that runs the decision before the agent's redrive or delete tool executes
- `README.md`: how to drop it into another agent in about 10 lines

**Reuse rule:** keep the options; change only the state builder and thresholds for a new message source.

## Originality, risks and success metrics

The concept is distinct from the known submissions because it decides recovery actions on queued data, not alerts, prompts or code; originality against the full gallery is still unverified.

| Closest known project | Its decision | DLQ Judge's difference |
| --- | --- | --- |
| SentryMesh, CloudOps Rapid Sentinel | Incident triage from alerts | Acts per message on queue data, with recovery actions |
| OpsGuard, Aegis-2B | Allow or block an agent action | Picks among 5 recovery actions, not allow/block |
| Refund Guard | Evidence-based approval | Infrastructure domain, batch scale, benchmarked against baselines |

**Risks**

| Risk | Mitigation |
| --- | --- |
| Decider misclassifies with high confidence | Dry-run default, discard needs ≥ 0.90 and an idempotency key |
| A similar project appears in the gallery | Check the gallery before building; lead the demo with batch speed and the benchmark |
| Synthetic data looks staged | Publish the labelled dataset and seed script |
| Decider needs a local GPU or fast laptop | Test early on the dev machine; keep batch size small |
| Bedrock cost creep | Cap Bedrock calls per run; log every call |

**Success metrics for the MVP**

- Zero unsafe actions on the 300-message set
- Fewer Bedrock calls than approach B, with accuracy reported honestly against both baselines
- Full triage of 300 messages in a single demo take under 3 minutes
