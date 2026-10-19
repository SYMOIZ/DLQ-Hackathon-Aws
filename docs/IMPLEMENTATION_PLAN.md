# IMPLEMENTATION_PLAN.md — DLQ Judge

Document version: 1.1 · Date: 2026-10-18 · Status: Draft (P0-T7 path + P5 entry OQs updated)

Nine phases over **13 working days** for one engineer working with Cursor. Day 1 = first working day after the documentation set is approved. Finish at least 2 days before the hackathon deadline (OQ-02).

Rules: one phase at a time; each task ends with its verification; each phase ends with its gate (`CURSOR_CONTEXT.md §7`). Record results in `docs/PROGRESS.md`.

---

## Timeline

| Phase | Name | Days | Depends on | Touches AWS? |
|---|---|---|---|---|
| P0 | Setup, spikes, mockup reconciliation | D1 | Docs approved | Read-only + 1 Bedrock call |
| P1 | Infrastructure and synthetic data | D2 | P0 | Creates stack, seeds DLQ |
| P2 | Decision core | D3–D4 | P1 | No (unit tests) / Decider local |
| P3 | Actions, run files, apply, restore | D5 | P2 | Integration tests only |
| P4 | Bedrock, clusters, agent, pattern | D6–D7 | P3 | Bedrock |
| P5 | UI server, API, screens S1–S3 | D8–D9 | P4 + `UI_SPEC.md` Approved | No (fixtures) |
| P6 | Screens S4–S5, benchmark | D10 | P5 | Bedrock |
| P7 | QA, security, UAT | D11 | P6 | Yes |
| P8 | Release, article, video, teardown | D12–D13 | P7 | Teardown |

```
P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8
                         ▲
        UI_SPEC Approved ┘ (blocking for P5)
```

---

## P0 — Setup, spikes, mockup reconciliation (D1)

**Entry:** documentation set approved by the user.

| Task | Steps | Verification |
|---|---|---|
| P0-T1 Repo skeleton | Create structure in `ARCHITECTURE.md §3` (empty modules with docstrings), `LICENSE` (Apache-2.0), `.gitignore`, `.env.example` (all vars from REQUIREMENTS §7, placeholders), `pyproject.toml` (3 runtime deps, dev extras `pytest`, `pytest-cov`, console script `dlq-judge = dlq_judge.cli:main`) | `pip install -e ".[dev]"` succeeds; `pytest -q` runs (0 tests) |
| P0-T2 Context files | Create `docs/PROGRESS.md`, `DECISIONS.md`, `OPEN_QUESTIONS.md` (copy OQ table), `CHANGELOG.md` | Files exist |
| P0-T3 Decider spike | Start `strands-decider serve … --port 8000`; send one request with the real question and 5 options; save request/response to `tests/fixtures/decider_request.json` / `decider_response.json`; check bind address (`lsof -i :8000` or `ss -ltnp`); time 50 calls | Fixture files exist; `docs/spike-notes.md` has endpoint, schema, whether `confidence` is returned, bind address, median/p95 latency, hardware |
| P0-T4 Strands spike | In a scratch script, attach a trivial `InterventionHandler` to an `Agent` with a Bedrock model; confirm import paths, `before_tool_call` event fields (tool name, input), how handlers are registered | Notes in `spike-notes.md`; decision `D-00x` recorded |
| P0-T5 Bedrock check | Run `AWS_DEPLOYMENT.md §2` commands; choose model ID | Converse returns text; model ID in `DECISIONS.md` |
| P0-T6 Pin versions | Pin exact versions of the 3 runtime deps and 2 dev deps in `pyproject.toml` | `pip install -e ".[dev]"` from clean venv works |
| P0-T7 Mockup reconciliation | `CURSOR_CONTEXT.md §6`: mockup at `design/mockup/`; fill `UI_SPEC.md §10`; propagate; user approves | `UI_SPEC.md` status **Approved** (2026-10-18) |
| P0-T8 Originality check | Search the hackathon gallery for SQS/DLQ triage projects | Result in `DECISIONS.md` |

**Deliverables:** skeleton repo, fixtures, spike notes, pinned deps, context files.
**Gate P0 (PASS needs all):** P0-T1–T6 verified · TC-Q03 pass · OQ-03, OQ-04, OQ-11 answered. P0-T7 may stay open until the P5 gate.

---

## P1 — Infrastructure and synthetic data (D2)

**Entry:** P0 gate PASS.

| Task | Steps | Verification |
|---|---|---|
| P1-T1 Template | Write `infra/template.yaml` exactly as `AWS_DEPLOYMENT.md §3` | `aws cloudformation validate-template` OK |
| P1-T2 Budget | `AWS_DEPLOYMENT.md §4` | `describe-budget` returns it |
| P1-T3 Deploy | `AWS_DEPLOYMENT.md §5`, §5.1 | Stack `CREATE_COMPLETE`; `sts get-caller-identity --profile dlqj` shows `dlqj-runner` |
| P1-T4 Teardown proof | Delete and redeploy once | `AWS_DEPLOYMENT.md §10` pass commands, then redeploy OK |
| P1-T5 Config + models | `config.py`, `models.py` (enums, dataclasses for all §5 contracts, reason → decided_by map) | TC-U30, TC-U31 pass |
| P1-T6 Generator | `bench/generate.py` per `TESTING_QA_UAT.md §8` (seeded, deterministic, example.com emails, Luhn-invalid numbers, 10 holdout per type) → `bench/dataset/messages.jsonl` | Running twice gives identical file (hash); counts per type correct |
| P1-T7 aws_io + seed | `aws_io.py` (allowlist, receive/send/delete/visibility, S3 put/get/list); `cli seed` (FR-20) | TC-U26 pass; TC-I06 pass |
| P1-T8 Doctor | `cli doctor` (FR-19) | TC-I09 pass |

**Deliverables:** deployed stack, dataset, seed + doctor commands.
**Gate P1:** TC-U26, TC-U30, TC-U31, TC-I06, TC-I09 pass; 300 messages visible in the DLQ.

---

## P2 — Decision core (D3–D4)

**Entry:** P1 gate PASS.

| Task | Steps | Verification |
|---|---|---|
| P2-T1 Masking + state | `masking.py`, `state.py` (ARCHITECTURE §5.4) | TC-U01–U06 pass |
| P2-T2 Pattern question | `patterns/failed_message_recovery/question.py`: `QUESTION`, `OPTIONS`, `render_state()` | TC-U33 pass |
| P2-T3 Decider client | `decider_client.py` using the P0 schema; confidence formula fallback; timeout handling | TC-U15, TC-U28 pass |
| P2-T4 Policy | `patterns/…/policy.py::decide()` and `dlq_judge/policy.py` re-export; bands, discard guard, missing evidence | TC-U07–U13 pass |
| P2-T5 Runlog | `runlog.py`: run ID (`YYYYMMDDTHHMMSSZ`), atomic writes, summary computation, histogram | TC-U25, TC-U29 pass |
| P2-T6 Triage (dry run, no Bedrock yet) | `engine.triage()`; review-band messages temporarily escalate with `bedrock_cap` reason until P4 | TC-U14 pass; `dlq-judge triage` on 300 messages writes run files; DLQ depth unchanged after 300 s (TC-I05) |
| P2-T7 Accuracy check | Run C offline on non-holdout records; if accuracy is poor, adjust `render_state` labels (not thresholds yet); log every change in `DECISIONS.md` | Numbers in `PROGRESS.md` |

**Deliverables:** end-to-end dry-run triage with Decider.
**Gate P2:** TC-U01–U15, U25, U28, U29, U33 pass · TC-I05 pass · TC-Q02 ≥ 85% on modules touched.

---

## P3 — Actions, apply, restore (D5)

**Entry:** P2 gate PASS.

| Task | Steps | Verification |
|---|---|---|
| P3-T1 Actions | `actions.py` per ARCHITECTURE §5.6 (backup first, delete last) | TC-U21, TC-U27 pass |
| P3-T2 Apply | `engine.apply()` per §4.2 (re-receive, match by MessageId, release non-targets, not_found) | TC-U22, U35, U36 pass |
| P3-T3 CLI apply flow | `triage --apply`, `apply --run`, confirmation rules (SECURITY §4) | TC-U24 pass |
| P3-T4 Override | `engine.override()` per §4.3 | TC-U32, U34 pass |
| P3-T5 Restore | `engine.restore()` + `cli restore` | TC-I07 pass |
| P3-T6 Integration | Seed 30 → triage → apply | TC-I01 pass |

**Deliverables:** safe apply, override, restore.
**Gate P3:** listed tests pass · TC-Q02 ≥ 85% · manual check: a dry run never calls Send/Delete/ChangeVisibility (stub asserts).

---

## P4 — Bedrock, clusters, agent, pattern (D6–D7)

**Entry:** P3 gate PASS; Bedrock model ID recorded.

| Task | Steps | Verification |
|---|---|---|
| P4-T1 Bedrock client | `bedrock_client.py`: Converse, prompts (ARCHITECTURE §9), JSON parsing, retries, call counter + cap | TC-U16–U19 pass (stubbed); TC-I03 pass |
| P4-T2 Engine integration | Replace P2 temporary behaviour: review band → second opinion | TC-U16–U19 pass in engine |
| P4-T3 Clusters | `clusters.py`: grouping, top `DLQJ_MAX_CLUSTERS`, evidence check | TC-U20 pass; TC-I04 pass |
| P4-T4 Guard | `patterns/…/hook.py` using P0 findings | TC-U23 pass |
| P4-T5 Agent | `agent.py`, `cli agent` | TC-I08 pass |
| P4-T6 Pattern README | Reuse guide in ≤ 10 lines of code; question, options, thresholds, how to attach the guard | A fresh 20-line script using only the README runs (UAT-05 dry run) |

**Deliverables:** complete backend.
**Gate P4:** listed tests pass · full triage of 300 messages completes with `bedrock_calls ≤ DLQJ_BEDROCK_MAX_CALLS + DLQJ_MAX_CLUSTERS`.

---

## P5 — UI server, API, screens S1–S3 (D8–D9)

**Entry:** P4 gate PASS **and** `UI_SPEC.md` status `Approved`. OQ-05, OQ-06, OQ-07, OQ-08, OQ-16 answered by mockup reconciliation; OQ-10 and OQ-15 still need explicit user acceptance of provisional answers; OQ-17 (Settings out of scope) answered as D-001.

| Task | Steps | Verification |
|---|---|---|
| P5-T1 Fixture run | Build `tests/fixtures/run_sample/` (TESTING §1) | Validates with TC-U25 checks |
| P5-T2 Server | `ui_server.py`: bind 127.0.0.1, token, Host/Origin checks, headers, static files, endpoints in ARCHITECTURE §7 (benchmark endpoint returns sample for now) | TC-A01–A12, TC-S07, TC-S08 pass |
| P5-T3 Shell + S1 | `index.html`, `app.css` (tokens for UI-21, light/dark), `app.js`: navigation (UI-22), states (UI-23), S1 (UI-01–UI-04) | TC-UI01–UI07 pass |
| P5-T4 S2 | Table, chips, bars, filters, search (UI-05–UI-11) | TC-UI08–UI14 pass |
| P5-T5 S3 | Drawer, probabilities, Bedrock block, overrides, close (UI-12–UI-16c) | TC-UI15–UI17, UI20, UI23, UI24 pass |
| P5-T6 Apply from UI | Confirm dialog + apply endpoint; `--allow-apply` | TC-UI03, UI04 pass; TC-A07, A08 pass |
| P5-T7 Design check | Side-by-side screenshots vs mockup for S1–S3 | Differences listed and fixed or approved |

**Deliverables:** working UI for S1–S3.
**Gate P5:** all listed tests pass · TC-Q04 pass · no element exists that is not in `UI_SPEC.md`.

---

## P6 — Screens S4–S5, benchmark (D10)

**Entry:** P5 gate PASS.

| Task | Steps | Verification |
|---|---|---|
| P6-T1 S4 Clusters | UI-17 | TC-UI21 pass |
| P6-T2 Baselines | `baseline_rules.py` (commit before any benchmark run), `baseline_bedrock.py` | Unit tests for rule mapping on 6 sample records |
| P6-T3 Runner | `run_bench.py`: 3 runs, metrics (TESTING §8), `results.json` + `results.md` | TC-B01–B05 pass |
| P6-T4 Threshold review | If needed, tune `DLQJ_AUTO_MIN`/`REVIEW_MIN` on non-holdout only; record in `DECISIONS.md`; rerun | Holdout untouched; decision logged |
| P6-T5 S5 Benchmark | UI-18 using real or sample results | TC-UI22 pass |
| P6-T6 Sample file | `sample_results.json` with round fake numbers, `sample_data: true` | TC-A09 pass |

**Deliverables:** all 5 screens; benchmark results.
**Gate P6:** listed tests pass · TC-UI18, UI19 pass with real 300-message run.

---

## P7 — QA, security, UAT (D11)

**Entry:** P6 gate PASS.

| Task | Steps | Verification |
|---|---|---|
| P7-T1 Full suites | Unit, API, integration (fresh stack) | TC-Q01, Q02, Q04, Q05; all TC-I pass |
| P7-T2 Security | SECURITY §9 checklist | TC-S01–S09 pass |
| P7-T3 Browser matrix | TC-UI01–UI30 in Chrome, Firefox, Safari, light + dark | All pass |
| P7-T4 UAT | TESTING §9 with 2 testers | UAT-01–04 pass; blockers fixed |
| P7-T5 Docs sync | Update every doc for changes made since P0 | TC-Q05 pass |

**Gate P7:** every test ID in `TESTING_QA_UAT.md` passes or has a user-approved waiver in `DECISIONS.md`.

---

## P8 — Release, article, video, teardown (D12–D13)

**Entry:** P7 gate PASS.

| Task | Steps | Verification |
|---|---|---|
| P8-T1 Demo script | `docs/demo-script.md`: under 3 min — problem (15 s), dry-run triage of 300 messages (40 s), UI summary + one drawer with Bedrock second opinion (50 s), benchmark screen (30 s), pattern code (20 s), close (10 s) | Timed rehearsal < 2:50 |
| P8-T2 Record video | Fresh stack, seed 42, record, upload publicly | Public URL works logged out |
| P8-T3 Article | `docs/article-draft.md` → Builder Center: problem, why a decision model, the pattern, benchmark (honest), lessons; tags `#strands-decider-2b`, `#policy` | Published URL |
| P8-T4 Release | README final, `results.md` committed, secret scan, tag `v1.0.0`, repo public, release notes | TC-S06, TC-Q03 pass |
| P8-T5 Submit | Hackathon submission form with repo, article, video | Confirmation received |
| P8-T6 Teardown | `AWS_DEPLOYMENT.md §10` | TC-I10 pass |

**Gate P8 = release:** all items in `REQUIREMENTS.md §10` ticked.

---

## Risks to the schedule

| Risk | Early signal | Fallback (keeps submission valid) |
|---|---|---|
| Decider schema or latency differs from docs | P0-T3 | In-process model load; smaller batch (100) for demo |
| Mockup reconciliation adds work | P0-T7 | Ask the user which mockup elements can move to a later version; never cut S1–S3 |
| Low Decider accuracy on holdout | P2-T7, P6-T3 | Raise `auto_min` so more goes to Bedrock; report honestly |
| Bedrock access delay | P0-T5 | Use another enabled small model; record decision |
| Schedule slip | Any gate late > 1 day | Drop UAT-05 and agent CLI polish; keep guard, pattern and UI S1–S3 |
