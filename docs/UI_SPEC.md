# UI_SPEC.md — DLQ Judge Local UI

Document version: 1.2 · Date: 2026-10-18 · **Status: Approved** · Approver: project author (user) · Approved date: 2026-10-18

> **Source of truth.** Approved mockup: `design/mockup/DLQ Judge.dc.html` (with `design/mockup/support.js`). Bundled copy: `design/mockup/DLQ Judge (standalone).html`. Reconciled in Phase 0 (P0-T7); all 26 rows in §10 accepted. Mockup wins over this spec for S1–S5 and shared chrome, except where `SECURITY.md` or `REQUIREMENTS.md` NFR-03 forbids CDN fonts / multi-account / auth (those stay out of v1.0; see §11).
>
> Tags:
> - `DESIGN` — in the approved mockup and in v1.0 scope; build it.
> - `GAP` — needed for the UI to work or to meet `SECURITY.md`, but not shown in the mockup; use only the stated provisional behaviour until approved.
> - `NOT IN DESIGN` — do not build in v1.0 (includes mockup vision deferred to §11).

---

## 1. Global

| ID | Element | Spec | Tag |
|---|---|---|---|
| UI-19 | Themes | Light and dark via explicit **Light / Dark** toggle in the left sidebar (mockup). Persist preference in `localStorage` key `dlqj-theme`. On first visit, fall back to `prefers-color-scheme` | DESIGN |
| UI-20 | Layout | Desktop first; left sidebar 232 px + main; min width 1280 px; reference 1440 px; no mobile layout | DESIGN |
| UI-21 | Action colours | CSS custom properties matching mockup tokens: Redrive now = blue (`--a-now`) · Redrive later = teal (`--a-later`) · Quarantine = amber (`--a-quar`) · Discard duplicate = gray (`--a-disc`) · Escalate to human = red (`--a-esc`). Light and dark values; chip text contrast ≥ 4.5:1 | DESIGN |
| UI-22 | Navigation | Left sidebar under heading **Workspace**: buttons `Run summary`, `Messages` (shows message count), `Failure clusters` (shows cluster count), `Benchmark`. Active item sunk background. Client-side switch via URL hash (`#summary`, `#messages`, `#clusters`, `#benchmark`). Drawer opens over Messages. **Settings** nav item exists in the mockup but is **NOT IN DESIGN** for v1.0 (§11) | DESIGN (four screens) |
| UI-23 | Loading / empty / error states | Not fully designed. Provisional: one line of plain text in the content area: `Loading…`, screen-specific empty strings in §8, `Could not load data: <error code>` | GAP |
| UI-24 | Brand / sidebar chrome | Logo mark + **DLQ Judge** + subtitle `v0.3 · local CLI report`. Footer panel: Decider / Bedrock / **Call cap** / Discard min — all read-only from `GET /api/run` (e.g. `thresholds.bedrock_max_calls`, `thresholds.discard_min`, model fields). **Never hardcode 50 or 60** in the UI. Theme toggle. No multi-account switcher, no profile menu in v1.0 (§11) | DESIGN (brand + status + theme) |
| UI-25 | Fonts | Mockup uses Geist via Google Fonts CDN. **v1.0:** system UI / monospace stacks only (NFR-03 / SECURITY — no CDN). Visual weight approximates the mockup | DESIGN (system fonts) · security override vs mockup CDN |
| — | Style | Clean, technical, AWS-console-adjacent. Plain HTML/CSS/vanilla JS; no npm, no frameworks, no CDN | DESIGN + NFR-03 |
| — | Data | Synthetic sample data only; no real company names or logos | DESIGN |

## 2. Screen S1 — Run summary (default view, `#summary`)

Shared header (all screens except Settings vision):

| ID | Component | Fields / behaviour | Backend dependency | Tag |
|---|---|---|---|---|
| UI-01a | Header: queue name | Monospace H1 from `queue` (e.g. `dlqj-orders-dlq`) | `GET /api/run` → `queue` | DESIGN |
| UI-01b | Header: run meta | Breadcrumb `Runs / <run_id>`; **Source** `source_queue`; **Started** localised from `started_at`; **Duration** from `started_at`–`finished_at` (e.g. `41.8 s`); optional **Quarantine** URI if bucket known (display-only string from config/summary when present) | `run_id`, `source_queue`, `started_at`, `finished_at`, optional `quarantine_uri` | DESIGN |
| UI-01c | Header: mode badge | `Dry run` (dashed pill) when `mode = "dry_run"`; `Applied` (green pill) when `mode = "applied"` | `mode` | DESIGN |
| UI-01d | Header: "Apply actions" button | Enabled only when `mode = "dry_run"` and `actionable_count > 0`. Opens **custom confirm modal** (UI-01e), not native `confirm()`. While pending after confirm: button disabled, label `Applying…`. On success: reload run, messages, clusters. On error: UI-23. When applied: replace with disabled/secondary control `Actions applied · view audit log` (audit = summary + decisions already on screen; no separate audit route in v1.0) | `actionable_count`, `POST /api/run/apply` | DESIGN |
| UI-01e | Apply confirm modal | Title `Apply <n> actions to <queue>?`; body notes equivalence to `--apply`; list of planned counts per action (exclude escalate); held text for escalated + blocked discards; **Cancel** / **Apply \<n\> actions**. On OK → `POST /api/run/apply` with `{"confirm":"APPLY","expected_actionable_count":n}`. Esc or scrim click closes without apply | counts from messages / summary | DESIGN (closes OQ-06) |
| UI-01f | Header: CLI hint | Read-only code chip showing example `$ dlq-judge triage --queue <queue>` | `queue` | DESIGN |
| UI-01g | Header: Export report | Button **Export report** (in mockup). v1.0: client-side download of JSON already loaded in the page (`/api/run` + `/api/messages` + `/api/clusters` responses). **No new endpoint, no server export code.** If that is insufficient for a useful file, drop the button and log in OPEN_QUESTIONS | client-side only | DESIGN |
| UI-02 | Five action cards | Label, count, % of `processed` (1 decimal as mockup), short description, colour bar. Discard card shows note `N held: confidence < 0.90` when any discard is below threshold. **Click** navigates to `#messages` with that action filter | `counts.*`, `processed` | DESIGN |
| UI-03 | Stat strip (4 cells) | (1) Messages processed `processed` with subline `scored · routed by rule` from `scored_count` / `rule_count`; (2) Median decision latency `median_decider_ms` + subline p95; (3) Bedrock calls `bedrock_calls` vs `baseline_bedrock_calls` + subline second opinions / cluster diagnoses when fields present; (4) horizontal compare bars DLQ Judge vs baseline | summary fields in §ARCHITECTURE 5.8 | DESIGN |
| UI-04 | Confidence distribution | Histogram: **28 bins** of width **0.025** over confidence **0.30–1.00** (messages with confidence &lt; 0.30 fold into the first bin; null excluded). Three shaded bands with labels; right sidebar lists band counts including **Missing attributes** (rule). Drawn as inline SVG/DOM by vanilla JS | `confidence_histogram` (28 integers), `band_counts` optional | DESIGN |

## 3. Screen S2 — Message table (`#messages`)

| ID | Component | Fields / behaviour | Backend dependency | Tag |
|---|---|---|---|---|
| UI-05 | Table columns (in order) | Message ID (short prefix ~13 chars, full ID in `title`) · Error type · Recv · Action (chip) · Confidence (bar) · Decided by · Status | `GET /api/messages` → `items[]` | DESIGN |
| UI-06 | Action chip | Label + UI-21 colour + colour dot. If action is `discard_duplicate` and confidence &lt; 0.90 (or null): badge `⚠ <0.90` | `action`, `confidence` | DESIGN |
| UI-07 | Confidence bar | Horizontal bar with 0.60 / 0.85 markers; numeric value 2 decimals; null → `—` | `confidence` | DESIGN |
| UI-08 | Decided by | `Decider`, `Decider + Bedrock`, or `Rule` | `decided_by` | DESIGN |
| UI-09 | Status | Primary: `Planned`, `Applied`, `Skipped`, `Failed` from `status`. If `overridden` true while still planned: show **Overridden** (closes OQ-05). Optional mockup variants `Blocked · held in DLQ` / `Flagged` are display aliases for planned discard-below-threshold / escalate — allowed as secondary labels only when they match those cases | `status`, `overridden`, `action`, `confidence` | DESIGN |
| UI-10a | Filter: action | Chip row: `All` + 5 actions with counts (not a select) | client-side on `action` | DESIGN |
| UI-10b | Filter: confidence band | Select: `All confidence bands`, `≥ 0.85 · auto-act`, `0.60–0.85 · Bedrock check`, `< 0.60 · escalate`, `Not scored (rule)` | client-side on `band` / null confidence | DESIGN |
| UI-10c | Filter: error type | Select: `All error types` + distinct values | client-side | DESIGN |
| UI-10d | Search box | Placeholder `Search message ID or error text`; case-insensitive match on full message ID, `error_type`, `error_text` | client-side | DESIGN |
| UI-10e | Clear filters | Link **Clear** when any filter/search active | — | DESIGN |
| UI-10f | Pagination | Page size **25**. Footer: `Showing a–b of n`, **Previous** / **Next**, `Page N of M`. Hint: `Click a row to inspect the decision · Esc closes` | client-side | DESIGN (closes OQ-08) |
| UI-11 | Row click | Opens detail drawer (S3) | — | DESIGN |
| — | Column chooser, export CSV | — | — | NOT IN DESIGN |

Filters combine with AND. Filter state is not persisted across reloads (hash may retain screen only).

## 4. Screen S3 — Message detail drawer (opens over S2)

| ID | Component | Fields / behaviour | Backend dependency | Tag |
|---|---|---|---|---|
| UI-12 | Message body | Masked body (`body_masked`), monospace; pretty-printed if valid JSON; scrolls. Never unmasked. Caption: `PII masked before leaving this machine` | `GET /api/messages/{id}` → `body_masked` / `state.body_masked` | DESIGN |
| UI-13 | Error attributes | Table rows: ErrorType, ErrorMessage, ApproximateReceiveCount, SourceQueue, MessageAge, IdempotencyKey (present/absent) | `state.*` | DESIGN |
| UI-14 | Option probabilities | Five horizontal bars in fixed option order; value with 2–3 decimals; chosen option bold; 0.60/0.85 markers. If null: dashed box `Decider was not called: the message has no error attributes. Escalated by rule.` (or reason text from `reason`) | `probabilities`, `choice`, `reason` | DESIGN |
| UI-15 | Bedrock second opinion | Shown only if `bedrock` not null: pick label, reason, `Agrees with Decider` / `Disagrees → escalated` | `bedrock.*` | DESIGN |
| UI-16 | Override buttons | Five buttons; current selected. Enabled only when `mode = "dry_run"` and status allows override. Click → `POST /api/messages/{id}/override`. Discard below 0.90 shows warning banner (OQ-09: allowed) | `POST …/override` | DESIGN |
| UI-16b | Overridden state | Status **Overridden**; link **Revert to model decision (\<original label\>)** → POST override with previous action or clear via API (see ARCHITECTURE: set action back to `override.previous_action` and clear override) | `override` | DESIGN (closes OQ-05) |
| UI-16c | Close | `×` in drawer header, scrim click, and `Esc` | — | DESIGN |

## 5. Screen S4 — Failure clusters (`#clusters`)

| ID | Component | Fields / behaviour | Backend dependency | Tag |
|---|---|---|---|---|
| UI-17a | Cluster card | Two-column layout: left — Quarantine chip, `error_type`, sample error text, count, % of quarantined, sample ID buttons (open drawer); right — claims + fix | `GET /api/clusters` → `items[]` | DESIGN |
| UI-17b | Root-cause summary | Numbered claims; each may cite message ID buttons; unverified claims show tag `Unverified · no cited evidence` | `root_cause` / structured claims if present; else single claim from `root_cause` + `evidence_message_ids` | DESIGN |
| UI-17c | Suggested fix | Boxed text | `suggested_fix` | DESIGN |
| UI-17d | Unverified tag | As mockup | `unverified_claims[]` | DESIGN |
| UI-17e | Usage line | Optional Bedrock usage/latency text when present on cluster | `bedrock_latency_ms` / optional usage fields | DESIGN |
| — | Cluster bulk actions | — | — | NOT IN DESIGN |

Empty: UI-23 text `No failure clusters in this run.`

## 6. Screen S5 — Benchmark (`#benchmark`)

| ID | Component | Fields / behaviour | Backend dependency | Tag |
|---|---|---|---|---|
| UI-18a | Comparison table | Columns: Metric + Rules / Bedrock only / DLQ Judge. Rows: Accuracy, Unsafe-action rate, Median latency, p95 latency, Bedrock calls / 1,000 msgs. Cell bars + **Best** badge on winning cell | `GET /api/benchmark` → `approaches[]` | DESIGN |
| UI-18b | Sample-data label | Banner `Sample data · placeholder numbers` when `sample_data = true` | `sample_data` | DESIGN |
| UI-18c | Run details / meta | Hardware, models, region, date under or beside the table | `meta` | DESIGN |
| UI-18d | Accuracy by failure type | Secondary table/bars from `per_failure_type` | `per_failure_type` | DESIGN |
| UI-18e | Calibration panel | Accuracy within confidence bands for DLQ Judge when provided in results; if absent, hide panel | optional `calibration` in results | DESIGN if present · GAP hide if missing |

## 7. What the UI never does

- Start a triage run, seed, restore or tear down (CLI only).
- Show unmasked message bodies.
- Edit thresholds, model IDs or any configuration (Settings vision deferred — §11).
- Show any run other than the one the server was started with (A-08, OQ-10).
- Call AWS or Bedrock directly (only the local API does).
- Multi-account switching, login/logout, profile, 2FA, CLI tokens (mockup only — §11).

## 8. States per screen

| Screen | Loading | Empty | Error | Read-only |
|---|---|---|---|---|
| S1 | UI-23 text | `processed = 0` → cards show 0, chart empty, Apply disabled | UI-23 error text | `mode = "applied"` → Apply replaced by applied control |
| S2 | UI-23 text | No messages: `No messages in this run.` · Filtered none: `No messages match these filters.` | UI-23 | — |
| S3 | `Loading…` inside drawer | n/a | Error text inside drawer | `mode = "applied"` → overrides disabled |
| S4 | UI-23 | `No failure clusters in this run.` | UI-23 | — |
| S5 | UI-23 | n/a (sample file always present) | UI-23 | — |

## 9. Accessibility minimum

All controls reachable by keyboard; visible focus outline; buttons are `<button>`; table uses semantic grid or `<table>` with headers; chips include text (colour is never the only signal); chart has an `aria-label` summary (`Confidence distribution: <a> auto, <b> Bedrock check, <c> escalate`); Esc closes drawer and apply modal.

## 10. Reconciliation log (Phase 0 · 2026-10-18)

Mockup path: `design/mockup/DLQ Judge.dc.html`.

| # | Screen | Element | Spec says (v1.0 brief) | Mockup shows | Resolution | Date |
|---|---|---|---|---|---|---|
| 1 | Global | Navigation | Plain text link row (GAP OQ-16) | Left sidebar with counts + Settings | Adopt sidebar for 4 screens; Settings → §11 out of scope | 2026-10-18 |
| 2 | Global | Theme | `prefers-color-scheme` only | Explicit Light/Dark toggle | Adopt toggle + localStorage; OS as first-visit fallback | 2026-10-18 |
| 3 | Global | Fonts | System fonts, no CDN | Geist via Google Fonts | Keep system fonts (SECURITY/NFR-03); log design gap | 2026-10-18 |
| 4 | Global | Sidebar status | Not specified | Decider / Bedrock / Call cap / Discard min panel | Adopt read-only panel (UI-24) | 2026-10-18 |
| 5 | S1 | Apply confirm | Native `confirm()` (GAP OQ-06) | Custom modal with per-action counts | Adopt custom modal (UI-01e); closes OQ-06 | 2026-10-18 |
| 6 | S1 | Header meta | Queue, time, duration, mode | + run breadcrumb, source, quarantine, CLI chip, Export | Adopt UI-01b/f/g | 2026-10-18 |
| 7 | S1 | Action cards | Count + % only | + description, colour bar, discard hold note, click→filter | Adopt | 2026-10-18 |
| 8 | S1 | Stat strip | 3 metrics | 4 cells + compare bars + sublines | Adopt; extend summary contract | 2026-10-18 |
| 9 | S1 | Histogram | 20 bins 0.00–1.00 | 28 bins 0.025 from 0.30–1.00 + policy sidebar | Adopt 28-bin histogram; update ARCHITECTURE | 2026-10-18 |
| 10 | S2 | Action filter | `<select>` | Chip buttons with counts | Adopt chips | 2026-10-18 |
| 11 | S2 | Confidence filter | 3 bands | + Not scored (rule) | Adopt | 2026-10-18 |
| 12 | S2 | Pagination | NOT IN DESIGN (OQ-08) | 25/page Previous/Next | Adopt pagination; closes OQ-08 | 2026-10-18 |
| 13 | S2 | Discard warn | `⚠ Below 0.90` | `⚠ <0.90` | Adopt mockup wording | 2026-10-18 |
| 14 | S2 | Status | Planned/Applied/Skipped/Failed | Also Overridden / Blocked / Flagged | Adopt Overridden; aliases for blocked/flagged as in UI-09 | 2026-10-18 |
| 15 | S2 | Empty filtered | Generic empty | `No messages match these filters.` | Adopt | 2026-10-18 |
| 16 | S3 | Override display | No badge (GAP OQ-05) | Overridden + Revert link | Adopt; closes OQ-05 | 2026-10-18 |
| 17 | S3 | Close | GAP | ×, scrim, Esc | Adopt DESIGN | 2026-10-18 |
| 18 | S3 | Prob null text | Short rule text | Dashed box about missing attributes | Adopt mockup copy | 2026-10-18 |
| 19 | S4 | Layout | Flat cards | Two-column + numbered claims + sample buttons | Adopt | 2026-10-18 |
| 20 | S5 | Layout | Simple 3×N table | Transposed metrics, Best, per-type, calibration | Adopt UI-18a–e | 2026-10-18 |
| 21 | S5 | Sample label | `Sample data` | `Sample data · placeholder numbers` | Adopt mockup banner text | 2026-10-18 |
| 22 | — | Settings / accounts / profile / auth | Not in brief | Full Settings screens | **Out of scope v1.0** (§11); NOT IN DESIGN | 2026-10-18 |
| 23 | — | Multi-account switcher | Single account (REQUIREMENTS) | Account dropdown in sidebar | Out of scope v1.0 | 2026-10-18 |
| 24 | — | Call cap display | Env default 50 | Mockup shows 60 | Keep `DLQJ_BEDROCK_MAX_CALLS` default **50**; sidebar shows actual config value | 2026-10-18 |
| 25 | — | Queue name example | `dlqj-…` prefix | `orders-dlq` without prefix | Backend FR-17 unchanged; UI displays configured queue name | 2026-10-18 |
| 26 | Global | Loading states | GAP OQ-07 | Still not fully designed | Remain GAP (UI-23); closes OQ-07 as accepted provisional | 2026-10-18 |

When the user confirms this document, change Status to `Approved`, record approver and date.

## 11. Mockup vision deferred (v1.0 out of scope)

Present in `design/mockup/DLQ Judge.dc.html` but **not** built for hackathon v1.0 (REQUIREMENTS §3: no multi-account, no auth). Documented so implementers do not invent partial clones:

- Settings tabs: Profile, Preferences, Accounts and connectors, Policy and limits
- Multi-account switcher, connection banners, Retest / Disconnect
- Profile / 2FA / sessions / delete profile / Log out
- CLI tokens, notification toggles, editable limits
- Marketing site (`DLQ Judge Site.dc.html`) — reference only

Decision: `docs/DECISIONS.md` D-001.
