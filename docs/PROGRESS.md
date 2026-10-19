# PROGRESS.md — DLQ Judge

Updated: 2026-10-18

## Milestones

| Milestone | Scope | Result |
|---|---|---|
| M1 | P0–P3 backend + Decider | **PASS** — stack + Cognito; Decider 2B serving; unit tests 25 pass; apply/restore on 30 |
| M2 | P4–P5 Bedrock + UI S1–S3 + Cognito login | **PASS** — Nova Micro second opinion + clusters; UI + Cognito signup/login; API 401 without login |
| M3 | P6 S4–S5 + benchmark | **PASS** — clusters/benchmark screens; `bench/results/results.md` written |
| M4 | P7–P8 light QA + release | **PASS** — doctor all PASS; COST_REPORT; demo-script; stack left deployed |

## Gates

- P0: Decider fixtures + spike notes updated; Nova Micro chosen (D-00x).
- P1: Stack `UPDATE_COMPLETE` with Cognito; budget `dlq-judge`; seed 300.
- P2–P3: Policy/masking/state/actions/engine unit tests; TC-I01 style apply 30 + restore 30.
- P4: TC-I03/I04 pass; agent deny path TC-I08.
- P5–P6: UI + Cognito; recorded demo walkthrough replaces manual checklist; UAT-05 skipped.
- P7–P8: Doctor PASS; COST_REPORT; no teardown.

## Notes

- Decider System One schema uses `questions` dict + `criteria` (not `options` list).
- Dry-run visibility is 300 s — apply must wait for messages to reappear.
- Cognito: email sign-up + verification code; App Client `USER_PASSWORD_AUTH`.
