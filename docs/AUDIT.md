# Audit — DLQ Judge (2026-10-18)

## Broken / incomplete vs new deploy requirements

| Item | Status | Action |
|---|---|---|
| Git repo | Missing | `git init` + commit |
| Local unit tests | PASS (25) | Keep |
| Cognito login + 401 on `/api/*` | Works locally | Require Cognito on HTML pages too for public deploy |
| Host/Origin lock to 127.0.0.1 | Blocks CloudFront | Allow CloudFront Host + optional `DLQJ_PUBLIC_HOST` |
| Background triage/apply jobs | Missing | Add `jobs.py` + poll endpoints (<20s) |
| Queue-by-ARN | Missing | Validate same account/region + `dlqj-` prefix |
| EC2 + systemd + SSM | Missing | Add to `infra/template.yaml` |
| CloudFront HTTPS public URL | Missing | Add distribution + CF prefix-list SG |
| Extra queues (payments/shipping) | Missing | Add to template for E2E |
| GPU quota (G/VT) | **0.0** in us-east-1 | Use CPU `t3.xlarge`; document |
| Idle cost (EC2 while running) | Violates prior idle-$0 | User now requires EC2; stop instance at end |

## Decide

- Instance: **t3.xlarge** (CPU) — GPU On-Demand G/VT quota is 0.
- Public URL: CloudFront `https://*.cloudfront.net`
- App listens HTTP :8765; CloudFront origin HTTP :8765; SG allows only CloudFront origin-facing prefix list on 8765.
