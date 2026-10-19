# CURSOR_CONTEXT.md — How Cursor Must Work on DLQ Judge

> **Read this file first, every session.** It tells you which documents are authoritative, in what order to read them, how to execute work in phases, how to validate each step, and how to keep the documentation in sync.

Document version: 1.1 · Date: 2026-10-18 · Status: Draft — mockup reconciled in UI_SPEC 1.1 (awaiting user approval)

---

## 1. What you are building (one paragraph)

DLQ Judge is a local Python agent that triages failed messages in an Amazon SQS dead-letter queue (DLQ). For every message, **Strands Decider 2B** (a small local decision model) picks one of five recovery actions and returns a confidence score. Deterministic policy code decides whether to act, ask **Amazon Bedrock** for a second opinion, or escalate to a human. Bedrock also explains clusters of permanently failing ("poison") messages. Results are shown in a **local web UI** (served only on `127.0.0.1`) that matches the approved mockup. Everything runs in **dry-run mode by default**. It is an entry for the AWS Strands Decider 2B Agent Experience Hackathon.

---

## 2. Document map and authority order

When documents disagree, the **higher** item wins. Report the conflict (§8) instead of choosing silently.

| Rank | Document | Authority over |
|---|---|---|
| 1 | Approved UI mockup (external file, see §6) | What the UI shows and does |
| 2 | `docs/UI_SPEC.md` | Written form of the mockup: screens, components, fields, states, backend dependencies |
| 3 | `docs/REQUIREMENTS.md` | Functional/non-functional requirements, IDs, acceptance criteria |
| 4 | `docs/SECURITY.md` | Security controls (can block any feature) |
| 5 | `docs/ARCHITECTURE.md` | Components, module boundaries, API and data contracts |
| 6 | `docs/IMPLEMENTATION_PLAN.md` | Phase order, tasks, deliverables, phase gates |
| 7 | `docs/AWS_DEPLOYMENT.md` | AWS resources, CLI commands, rollback |
| 8 | `docs/TESTING_QA_UAT.md` | Test cases, QA gates, benchmark, UAT |
| 9 | `README.md` | Quick start (summary only; never the source of a rule) |

**Exception:** `SECURITY.md` overrides any lower document *and* the UI on safety matters (e.g. dry-run default, confirmation before destructive actions). If a safety control requires a UI change that is not in the mockup, flag it as a design gap; do not add UI on your own.

---

## 3. Reading order

Read in this order at the start of the project:

1. `CURSOR_CONTEXT.md` (this file)
2. `README.md`
3. `REQUIREMENTS.md`
4. `UI_SPEC.md`
5. `ARCHITECTURE.md`
6. `SECURITY.md`
7. `IMPLEMENTATION_PLAN.md`
8. `AWS_DEPLOYMENT.md`
9. `TESTING_QA_UAT.md`

At the start of **each later session**, read: this file → `docs/PROGRESS.md` → the section of `IMPLEMENTATION_PLAN.md` for the current phase → any document that phase references.

---

## 4. Dependency hierarchy

### 4.1 Document dependencies

```
Approved mockup
   └─ UI_SPEC.md
        └─ REQUIREMENTS.md ◄── SECURITY.md
             └─ ARCHITECTURE.md (contracts)
                  ├─ IMPLEMENTATION_PLAN.md
                  ├─ AWS_DEPLOYMENT.md
                  └─ TESTING_QA_UAT.md
                        └─ README.md (summary)
```

A change at any level requires checking every document below it.

### 4.2 Code module dependencies (lower layers never import higher layers)

```
Layer 0  config.py, models.py                      (stdlib only)
Layer 1  masking.py, state.py, policy.py           (Layer 0)
Layer 2  decider_client.py, bedrock_client.py,
         aws_io.py                                 (Layer 0–1; boto3, urllib)
Layer 3  actions.py, runlog.py, clusters.py        (Layer 0–2)
Layer 4  engine.py (triage/apply/override/restore) (Layer 0–3)
Layer 5  ui_server.py (HTTP API + static files),
         agent.py + patterns/failed_message_recovery (Strands), cli.py
Layer 6  bench/ (uses Layer 1–4 directly)
```

### 4.3 Phase dependencies

Phase N may start only when Phase N−1's gate passes (see `IMPLEMENTATION_PLAN.md`). Exception: documentation updates may happen at any time.

---

## 5. Non-negotiable rules

1. **No coding before the docs are approved** and the Phase 0 gate passes.
2. **No AWS resource creation** outside the commands in `AWS_DEPLOYMENT.md`.
3. **Dry-run is the default.** No code path may send, delete or change visibility of an SQS message unless the run is in apply mode, triggered by the explicit apply flow in `SECURITY.md §4`.
4. **Synthetic data only.** Never point the tool at a queue not created by this project's stack (`dlqj-` prefix). The code must refuse other queue names (REQ FR-17).
5. **Runtime dependencies are exactly:** `strands-agents`, `strands-decider`, `boto3` (+ their transitive deps). **Dev dependencies are exactly:** `pytest`, `pytest-cov`. Anything else needs an entry in `docs/DECISIONS.md` and user approval. Frontend uses plain HTML, CSS and vanilla JavaScript; no npm, no frameworks, no CDN.
6. **No UI drift.** Implement only what `UI_SPEC.md` lists. Items marked `GAP` or `NOT IN DESIGN` must not be built until the user resolves them; use the documented provisional behaviour only where `UI_SPEC.md` explicitly allows it.
7. **No invented features.** If a task seems to need something not documented, stop and log it in `docs/OPEN_QUESTIONS.md`.
8. **Never commit secrets**, AWS account IDs, or real message data.
9. **The five action names are fixed:** `redrive_now`, `redrive_later`, `quarantine_poison`, `discard_duplicate`, `escalate_human`. Do not rename or add options.
10. **Bedrock never triggers an action alone.** It may only confirm or block Decider's choice.

---

## 6. Phase 0 blocking step: reconcile the approved mockup

**Done in P0-T7 (2026-10-18):** approved mockup is at `design/mockup/DLQ Judge.dc.html` (with `support.js`). `UI_SPEC.md` status is `Reconciled — awaiting user approval`. Settings / multi-account / auth from the mockup are deferred (UI_SPEC §11, D-001).

Before any UI work (Phase 5):

1. User must confirm reconciled `UI_SPEC.md` and mark status `Approved`.
2. If the user rejects a resolution in §10, update the spec and every affected doc in the same change set.

**Gate:** No Phase 5 or Phase 6 task (UI) may start while `UI_SPEC.md` status is not `Approved`. Backend phases (1–4) may proceed, but any API field may change after approval.

---

## 7. How to execute a phase

For every phase in `IMPLEMENTATION_PLAN.md`:

1. **Announce** the phase and list the tasks you will do in this session.
2. **Check entry criteria** (previous gate passed, required inputs present).
3. **Do one task at a time.** After each task:
   - run the task's verification command(s);
   - run `pytest tests/unit -q`;
   - fix failures before moving on.
4. **Never mix phases** in one change set, except doc fixes.
5. **At phase end**, run the phase gate checklist. Paste the command output summary into `docs/PROGRESS.md`.
6. **Stop and ask** the user before starting the next phase if anything was marked `FAIL` or `BLOCKED`.

### Commit convention

`<phase>-<task>: <short description>` e.g. `P2-T3: add policy bands and discard guard`. One logical task per commit.

---

## 8. Maintaining context (files Cursor creates and keeps updated)

Create these in Phase 0 and update them as you work:

| File | Purpose | Update when |
|---|---|---|
| `docs/PROGRESS.md` | Current phase, task status table (`TODO / DOING / DONE / BLOCKED`), gate results with dates | After every task |
| `docs/DECISIONS.md` | Numbered decisions (`D-001`…): context, decision, alternatives, who approved | Any choice not already fixed by the docs |
| `docs/OPEN_QUESTIONS.md` | Copy of the open questions from `REQUIREMENTS.md §9`, plus new ones; status `OPEN / ANSWERED` | New question or user answer |
| `docs/CHANGELOG.md` | Human-readable changes per phase | End of each phase |

Template for `docs/PROGRESS.md`:

```markdown
# Progress
Current phase: P2 — Decision core
| Task | Status | Verified by | Date |
|---|---|---|---|
| P2-T1 config + models | DONE | pytest tests/unit/test_config.py (8 passed) | 2026-10-21 |
## Gate results
| Phase | Result | Evidence | Date |
|---|---|---|---|
| P1 | PASS | TC-I06 ok, 300 msgs in DLQ | 2026-10-20 |
```

### When you find a conflict or gap

Write it in `docs/OPEN_QUESTIONS.md` like this and stop work on that item:

```
OQ-0xx | Source: UI_SPEC §4.3 vs SECURITY §4 | Problem: ... | Options: A/B | Blocking: yes/no | Status: OPEN
```

---

## 9. Updating documentation

- Any change to behaviour, contracts, env vars, commands or tests must update **all** affected docs in the **same commit**.
- Keep requirement IDs (`FR-`, `NFR-`, `UI-`, `TC-`, `OQ-`) stable. Never reuse a deleted ID; mark it `Removed`.
- Bump the `Document version` line at the top of any doc you change.
- After changing a contract in `ARCHITECTURE.md`, search all docs for the field or endpoint name and fix every mention.

---

## 10. Validation commands you will run often

```bash
pytest tests/unit -q                         # every task
pytest tests/unit --cov=dlq_judge --cov-report=term-missing   # end of phase
pytest tests/integration -q -m aws           # only when the phase says so (needs AWS)
python -m dlq_judge.cli doctor               # checks env vars, AWS identity, Decider, Bedrock access
python -m bench.run_bench --offline --seed 42  # Phase 6 onward
```

`doctor` is defined in `ARCHITECTURE.md §6`. It never changes AWS state.

---

## 11. Definition of done (whole project)

All items in `REQUIREMENTS.md §10 Release criteria` are ticked, `docs/PROGRESS.md` shows every gate `PASS`, and `docs/OPEN_QUESTIONS.md` has no `OPEN` item marked blocking.
