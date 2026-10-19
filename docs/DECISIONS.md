# Decisions

Numbered decisions (`D-001`…). Update when any choice is not already fixed by the docs.

---

## D-001 — Settings / multi-account / auth deferred from v1.0

| Field | Value |
|---|---|
| Date | 2026-10-18 |
| Context | Approved mockup includes Settings, multi-account, profile/auth. REQUIREMENTS §3 excludes them for the hackathon MVP. |
| Decision | v1.0 implements S1–S5 plus shared chrome only. Settings / multi-account UI remain **out of scope** (UI_SPEC §11). |
| Alternatives | Full Settings (rejected); stub “Coming soon” (rejected). |
| Approved by | User confirmation 2026-10-18 |
| Related | OQ-17, UI_SPEC §11 |

---

## D-002 — System fonts instead of Geist CDN

| Field | Value |
|---|---|
| Date | 2026-10-18 |
| Context | Mockup loads Geist from Google Fonts. NFR-03 forbids CDN. |
| Decision | System UI + monospace stacks only. |
| Approved by | User confirmation 2026-10-18 |
| Related | UI_SPEC UI-25, TC-UI24 |

---

## D-003 — Region, AWS profile, Bedrock model selection process

| Field | Value |
|---|---|
| Date | 2026-10-18 |
| Context | OQ-03 / deployment region and model choice. |
| Decision | **Region:** `us-east-1`. **Runner profile:** `AWS_PROFILE=dlqj` (SSO/admin profile supplied at P1). **Bedrock model:** not chosen in P0. In P0-T5, list small text models available in us-east-1 and run the Converse one-shot test on the **2 cheapest**. After P6 benchmark, pick the cheaper of those two if accuracy and unsafe-action results are equal (prefer 0 unsafe); record final ID here as D-003b. |
| Approved by | User 2026-10-18 |
| Related | OQ-03, AWS_DEPLOYMENT §2, P0-T5, P6 |

---

## D-004 — Dev hardware

| Field | Value |
|---|---|
| Date | 2026-10-18 |
| Context | OQ-04; Decider latency targets. |
| Decision | Hardware: **AMD Ryzen 5 7430U with Radeon Graphics**, **15 GB RAM**. Real Decider median/p95 measured in P0-T3 (`docs/spike-notes.md`). |
| Approved by | Detected + user template 2026-10-18 |
| Related | OQ-04, NFR-01 |

---

## D-005 — UI call-cap display and Export

| Field | Value |
|---|---|
| Date | 2026-10-18 |
| Context | Mockup shows Call cap 60; docs default `DLQJ_BEDROCK_MAX_CALLS=50`. Export button in mockup. |
| Decision | UI reads call cap from `GET /api/run` → `thresholds.bedrock_max_calls` (never hardcode 50/60). Doc default remains 50. Export remains client-side download of already-loaded API JSON only (UI-01g); no new endpoint. |
| Approved by | User 2026-10-18 |
| Related | UI-24, UI-01g, ARCHITECTURE §5.8 |

---

## D-006 — Originality check (P0-T8)

| Field | Value |
|---|---|
| Date | 2026-10-18 |
| Context | Search for existing SQS/DLQ triage projects overlapping this hackathon. |
| Decision | **No duplicate found** in the Strands Decider Agent Experience gallery for a local Decider-2B + Bedrock second-opinion DLQ triage CLI with five fixed actions and dry-run UI. Related prior art exists outside the gallery (Bedrock+Lambda DLQ triage articles; Bedrock+Step Functions DLQ blogs) but they are not Decider-2B local-decision agents. Closest gallery neighbour: CloudPilot AI (incident response categories, not SQS DLQ actions). Proceed; differentiate on Decider-first policy, local UI, and reusable FailedMessageRecovery pattern. |
| Sources | builder.aws.com hackathon page; `#strands-decider-2b` topic; public DLQ+Bedrock articles (Coder Legion, Serverless Guru) |
| Approved by | Agent P0-T8 2026-10-18 |

---

## D-007 — Pinned dependency versions (P0-T6)

| Field | Value |
|---|---|
| Date | 2026-10-18 |
| Decision | Runtime: `strands-agents==1.61.1`, `strands-decider==0.1.0`, `boto3==1.43.114`. Dev: `pytest==9.1.1`, `pytest-cov==7.1.0`. |
| Verified | `pip install -e ".[dev]"` in clean `.venv`; `pytest -q` → 0 tests |

---

## D-008 — Strands intervention API paths (P0-T4)

| Field | Value |
|---|---|
| Date | 2026-10-18 |
| Context | Docs referred to `InterventionHandler` / `before_tool_call`; need exact package paths for `strands-agents==1.61.1`. |
| Decision | Use `strands.interventions.handler.InterventionHandler` and `strands.interventions.actions` (`BeforeToolCallEvent`, `Deny`, `Proceed`). Register with `Agent(..., interventions=[...])`. Tool name from `event.tool_use["name"]`. |
| Alternatives | Old guessed paths `strands.agent.interceptor` / `strands.interceptors` — do not exist in 1.61.1. |
| Evidence | `scripts/spike_strands_handler.py`; `docs/spike-notes.md` |
