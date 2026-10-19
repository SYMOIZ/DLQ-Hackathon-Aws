# Demo walkthrough (recorded once — replaces manual UI checklist)

Target length: under 3 minutes.

1. **Problem (15 s)** — SQS DLQs pile up; manual triage is slow and unsafe.
2. **Dry-run triage (40 s)** — `dlq-judge seed --count 300` → `dlq-judge triage` → show `runs/<id>/summary.json`.
3. **UI (50 s)** — Sign up → email code → verify → login. Summary cards, open one message drawer with Bedrock second opinion, logout.
4. **Benchmark (30 s)** — Benchmark screen (Rules / Bedrock / DLQ Judge).
5. **Pattern (20 s)** — Show `patterns/failed_message_recovery/README.md` 10-line reuse.
6. **Close (10 s)** — Dry-run default; apply only with `--yes`.

Recording: one pass covering login + S1–S5; skip UAT-05 and agent CLI polish.
