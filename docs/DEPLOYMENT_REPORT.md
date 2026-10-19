# DEPLOYMENT_REPORT.md — DLQ Judge public deploy

Date: 2026-10-18 · Region: `us-east-1` · Profile: `default`  for CFN; app uses instance role `dlqj-ec2`.

## Instance type decision

| Option | On-Demand $/hr (us-east-1 Linux) | Notes |
|---|---|---|
| `t3.large` (CPU) | $0.0832 | 8 GiB — tight for Decider 2B |
| `t3.xlarge` (CPU) | **$0.1664** | **Selected** — 16 GiB for model + app |
| `g4dn.xlarge` (GPU) | n/a | **Quota Running On-Demand G and VT instances = 0.0** |

**Choice:** `t3.xlarge` (CPU). GPU quota is zero; reported as required.

## Resources created (stack `dlq-judge`)

- SQS: `dlqj-orders`, `dlqj-orders-dlq`, `dlqj-payments`(+dlq), `dlqj-shipping`(+dlq)
- S3: `dlqj-quarantine-<AWS_ACCOUNT_ID>`, `dlqj-deploy-<AWS_ACCOUNT_ID>`
- Cognito User Pool `dlqj-users` + App Client (no secret)
- IAM: `dlqj-ec2` (instance + SSM), `dlqj-runner` (local assume)
- EC2 `<EC2_INSTANCE_ID>` + 40 GiB gp3 (DeleteOnTermination=false)
- Security group: inbound TCP 8765 from CloudFront prefix list `pl-3b927c52` only (no SSH)
- CloudFront distribution `<CLOUDFRONT_DISTRIBUTION_ID>` → HTTP origin `:8765`

## Public URL

**https://<CLOUDFRONT_DOMAIN>/**

## Commands run (summary)

```bash
aws cloudformation deploy --stack-name dlq-judge --template-file infra/template.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides BedrockResourceArns=arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0 \
    InstanceType=t3.xlarge VpcId=<VPC_ID> SubnetId=<SUBNET_ID> \
    CloudFrontPrefixListId=pl-3b927c52 \
  --tags project=dlq-judge --region us-east-1

aws s3 cp dist/dlq-judge-app.tgz s3://dlqj-deploy-<AWS_ACCOUNT_ID>/app/
aws ssm send-command ... AWS-RunShellScript  # install + systemd
```

Windows note: if `aws` CLI is not on PATH, use boto3 scripts under `scripts/_qa_*.py` (same profile/region).

## PASS/FAIL (deploy + live QA)

| Step | Result | Evidence |
|---|---|---|
| Local unit tests | PASS | 28 passed |
| CFN deploy | PASS | `Successfully created/updated stack` |
| GPU quota check | PASS (CPU fallback) | G/VT quota 0.0 |
| Package upload | PASS | S3 `app/dlq-judge-app.tgz` |
| SSM install | PASS | Command Success; UI healthy |
| UI `/healthz` via CF | PASS | `{"ok": true, ...}` |
| Cognito + EC2 role | PASS after fix | Dropped required `AWS_PROFILE` on instance |
| Live E2E (`tests/e2e/live_qa.py`) | PASS | **29/29** — see `docs/QA_LIVE.md` |
| Stop/start durability | PASS | Runs + EBS kept; CF origin DNS refresh required |
| Hotfix override/`_latest_run_id` | PASS | Redeployed via package_app + S3 + SSM |

## Post-start checklist

1. Start instance `<EC2_INSTANCE_ID>`
2. Wait SSM Online + local `:8765/healthz`
3. Update CloudFront origin `ec2-ui` DomainName to current `PublicDnsName`
4. Wait distribution Status=Deployed
5. Hit public `/healthz`
