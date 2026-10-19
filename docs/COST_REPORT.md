# COST_REPORT.md — DLQ Judge (public EC2 + CloudFront)

Date: 2026-10-18 · Region: `us-east-1`

## Sources (retrieved 2026-10-18)

- EC2 On-Demand: AWS Price List API — `t3.xlarge` Linux us-east-1 **$0.1664/hr**; `t3.large` **$0.0832/hr**
- CloudFront: https://aws.amazon.com/cloudfront/pricing/ — HTTPS requests + data transfer (PriceClass_100)
- Cognito: https://aws.amazon.com/cognito/pricing/ — free tier 50k MAU (essentials)
- SQS: https://aws.amazon.com/sqs/pricing/ — $0.40 / million requests after 1M free
- S3: https://aws.amazon.com/s3/pricing/
- Bedrock Nova Micro: AWS ML blog / Bedrock pricing — ~$0.000035 / 1K input, $0.00014 / 1K output tokens
- EBS gp3: https://aws.amazon.com/ebs/pricing/ — ~$0.08/GB-mo

## Cost while running (EC2 started)

| Item | Rate | Notes |
|---|---|---|
| EC2 `t3.xlarge` | **$0.1664 / hour** | Selected (GPU G/VT quota = 0) |
| EBS 40 GiB gp3 | ≈ $0.0044 / hour | $0.08×40 / 730 |
| CloudFront | ≈ $0 (idle) | Pay per request/GB when used |
| Cognito | $0 within free tier | |
| **Approx running** | **≈ $0.17 / hour** | |

## Cost while stopped (EC2 stopped, not terminated)

| Item | Rate |
|---|---|
| EC2 compute | **$0 / hour** |
| EBS 40 GiB (kept) | ≈ $3.20 / month (~$0.0044/hr equivalent) |
| S3 quarantine + deploy | pennies (lifecycle 7d on quarantine) |
| CloudFront distribution | $0 idle |
| Cognito User Pool | $0 idle |
| SQS queues | $0 idle |
| **Approx stopped** | **≈ $0.00 compute; EBS ~$3.20/mo** |

## Per 1,000 messages (Bedrock + SQS + S3)

| Component | USD / 1,000 msgs |
|---|---|
| SQS (~3.5k requests) | ~$0.0014 |
| Bedrock Nova Micro (≤55 Converse) | ~$0.0014 |
| S3 PUT backups (~700) | ~$0.0035 |
| CloudFront (UI polling) | ≪ $0.01 typical demo |
| **Total variable** | **≈ $0.01** |

Decider runs on the EC2 instance (included in hourly rate above).

## Ops note (this QA cycle)

- Stop/start proven: EBS + `/opt/dlq-judge/runs` survive; public IP/DNS changes → **update CloudFront origin** after each start.
- Prefer stopped when idle to avoid the ~$0.17/hr compute charge.
