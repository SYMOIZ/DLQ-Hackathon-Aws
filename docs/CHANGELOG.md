# Changelog

Human-readable changes per phase.

---

## Phase 0 — 2026-10-18 (approvals + skeleton)

### User approvals

- UI_SPEC.md → **Approved** (all 26 §10 rows); approver = project author; date 2026-10-18.
- D-001 Settings out of scope confirmed.
- OQ-03: region `us-east-1`; Bedrock model deferred (P0-T5 shortlist 2 cheapest → P6 final).
- OQ-04: AMD Ryzen 5 7430U + Radeon Graphics, 15 GB RAM.
- `AWS_PROFILE=dlqj` (runner); SSO/admin at P1.
- OQ-09, OQ-10, OQ-15 provisionals accepted.
- Clarifications: call cap from API only; Export client-side only; revert contract confirmed (§7 + TC-A13); TC-U25/U29 match 28-bin summary; system fonts only.

### Consistency check (TC-Q05) after approvals

| Change | Detail |
|---|---|
| `thresholds.bedrock_max_calls` | Added to summary contract for UI-24 |
| UI-24 / D-005 | Never hardcode 50/60 |
| UI-01g | Export kept as client-side only |
| ARCHITECTURE §7 | Revert request/response/409 rules spelled out |
| TC-U25 | Explicit new summary fields + histogram length 28 |

### Skeleton (P0-T1 / T6)

- Repo modules, LICENSE, `.gitignore`, `.env.example`, `infra/*`, pinned `pyproject.toml`.
- Verified editable install + pytest (0 tests).

### Originality (P0-T8)

- D-006: no gallery duplicate for Decider-2B local DLQ Judge pattern.

---

## Phase 0 — 2026-10-18 (documentation bootstrap)

### Mockup and UI_SPEC (P0-T7)

- Moved approved mockup files into `design/mockup/` (`DLQ Judge.dc.html`, `support.js`, standalone and site HTML, product concept).
- Reconciled `UI_SPEC.md` → version **1.1**, status **Reconciled — awaiting user approval**.
- Filled §10 reconciliation log (26 rows); mockup wins for S1–S5; Settings/multi-account deferred (§11, D-001).
- Closed OQ-01, OQ-05, OQ-06, OQ-07, OQ-08, OQ-13, OQ-16, OQ-17.

### Propagated contract / test updates

- `ARCHITECTURE.md` 1.1: summary fields `scored_count`, `rule_count`, `bedrock_*_calls` split, `band_counts`, `discard_held_count`, `quarantine_uri`; histogram **28×0.025** over [0.30, 1.00]; override `reason`; revert API; benchmark optional `calibration`; stack component no longer claims a log group.
- `REQUIREMENTS.md` 1.1: FR-13/14, NFR-09, A-01, OQ table with Status column, release criteria.
- `TESTING_QA_UAT.md` 1.1: TC-U29 histogram; TC-UI01–UI31; TC-A13 revert.
- `SECURITY.md` 1.1: apply confirmation references custom modal UI-01e.
- `CURSOR_CONTEXT.md` 1.1: §6 marked done pending approval.
- `IMPLEMENTATION_PLAN.md` 1.1: P0-T7 path; P5 entry OQs; P7-T3 → TC-UI01–UI30.
- `README.md`: status + context/mockup links.

### Consistency-check fixes

| Fix | Detail |
|---|---|
| Histogram length | Spec/tests said 20 bins; mockup/ARCHITECTURE/TC-U29 now 28 bins |
| Apply confirm | Native `confirm()` → custom modal aligned across SECURITY, UI_SPEC, TC-UI04/28 |
| Discard badge text | `Below 0.90` → `<0.90` |
| Navigation | Text links → sidebar; tests TC-UI27 |
| Pagination | Was NOT IN DESIGN; now DESIGN + TC-UI26 |
| Override display | Was GAP; now Overridden + revert (TC-UI25, TC-A13) |
| CloudWatch log group | ARCHITECTURE §2 said “log group”; aligned with AWS_DEPLOYMENT “no log group” |
| TC-UI range | IMPLEMENTATION_PLAN P7 still said UI24; updated to UI30 (+ UI31 for loading) |
| Override schema | Added `reason: "human"` to match OQ-09 |
| Call cap display | Mockup shows 60; docs keep default **50** (`DLQJ_BEDROCK_MAX_CALLS`); sidebar shows config value |
| Fonts | Geist CDN rejected (D-002); system fonts; TC-UI24 notes no CDN required |

### Context files created

- `docs/PROGRESS.md`, `DECISIONS.md` (D-001, D-002), `OPEN_QUESTIONS.md`, `CHANGELOG.md` (this file).

---

## Delivery — 2026-10-18 (M1–M4)

### Behaviour changes

- Cognito User Pool + secretless App Client in `infra/template.yaml`; UI signup → email code → verify → login; `/api/*` returns **401** without a valid Cognito ID token (token + Host/Origin checks remain).
- Decider client uses System One schema: `questions` dict with choice `criteria` (not `options` list); default timeout 120 s for CPU.
- Dry-run apply waits for 300 s visibility; apply scan capped so a polluted DLQ cannot loop forever.
- Manual UI checklist replaced by `docs/demo-script.md`; UAT-05 and agent CLI polish skipped per speed rules.
- `docs/COST_REPORT.md` — cost per 1,000 messages from current AWS pricing pages.
