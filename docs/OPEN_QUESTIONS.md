# Open questions

Copy of REQUIREMENTS §9 plus session notes. Status: `OPEN` / `ANSWERED`.

| ID | Question | Blocks | Answer / recommendation | Status |
|---|---|---|---|---|
| OQ-01 | Provide the approved UI mockup file | P5 | `design/mockup/DLQ Judge.dc.html` (+ support.js, standalone). UI_SPEC Approved 2026-10-18 | ANSWERED |
| OQ-02 | Hackathon submission deadline | Timeline | Plan 13 working days; finish 2 days early. Need actual deadline from user. | OPEN |
| OQ-03 | Region and Bedrock model ID | P4 / P0-T5 / P6 | **Region:** `us-east-1`. **Model:** do not pick in P0. P0-T5 lists small text models in us-east-1 and converse-tests the 2 cheapest. Final model after P6 benchmark (cheapest with equal accuracy and 0 unsafe actions); record in DECISIONS.md | ANSWERED (region); model deferred to P6 |
| OQ-04 | Dev hardware | P0 | AMD Ryzen 5 7430U with Radeon Graphics, 15 GB RAM. Measure Decider latency in P0-T3 | ANSWERED |
| OQ-05 | Overridden row appearance | P5 | Status **Overridden** + revert (UI-16b) | ANSWERED |
| OQ-06 | Apply confirmation dialog | P5 | Custom modal (UI-01e) | ANSWERED |
| OQ-07 | Loading / empty / error states | P5 | Plain text provisional (UI-23) | ANSWERED |
| OQ-08 | Message table pagination | P5 | 25/page Previous/Next (UI-10f) | ANSWERED |
| OQ-09 | Override to discard below 0.90? | P4 | Allowed; warning shown; logged as human (`override.reason = "human"`) | ANSWERED |
| OQ-10 | Which run does the UI show? | P5 | `--run <id>`, default latest | ANSWERED |
| OQ-11 | Exact Decider server schema | P2 | Capture in P0-T3 fixtures | OPEN |
| OQ-12 | GitHub repo owner/name | P8 | Recommend `dlq-judge` under user account | OPEN |
| OQ-13 | Benchmark before real results | P6 | Sample data banner from mockup | ANSWERED |
| OQ-14 | UAT testers | P7 | 2 engineers not on the build | OPEN |
| OQ-15 | Re-click Apply after partial failure? | P5 | Yes; FR-18 idempotency; mode stays `dry_run` until all actionable done | ANSWERED |
| OQ-16 | Navigation control | P5 | Left sidebar (UI-22); Settings deferred | ANSWERED |
| OQ-17 | Build Settings / multi-account in v1.0? | P5 | No — D-001 / UI_SPEC §11 | ANSWERED |

## Config answers (user, 2026-10-18)

| Item | Value |
|---|---|
| `DLQJ_REGION` | `us-east-1` |
| `AWS_PROFILE` (runner) | `dlqj` |
| SSO/admin profile | Deferred to P1 |
| Bedrock model | Deferred: P0-T5 shortlist → P6 final pick |
| Hardware | AMD Ryzen 5 7430U + Radeon Graphics, 15 GB RAM |
