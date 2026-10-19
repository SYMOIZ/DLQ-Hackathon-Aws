# AWS_DEPLOYMENT.md — DLQ Judge

Document version: 1.0 · Date: 2026-10-18 · Status: Draft

All AWS resources are created and deleted with the AWS CLI using one CloudFormation stack. **Do not run any command in this file until Phase 1** (`IMPLEMENTATION_PLAN.md`), and never point the tool at resources outside this stack.

Placeholders: `<account-id>`, `<sso-profile>`, `<region>` (default `us-east-1`), `<model-id>`.

---

## 1. Prerequisites

| Item | Check command | Pass |
|---|---|---|
| AWS CLI v2 | `aws --version` | `aws-cli/2.x` |
| SSO login works | `aws sso login --profile <sso-profile>` then `aws sts get-caller-identity --profile <sso-profile>` | Returns your account ID |
| Region chosen | — | Recorded in `docs/DECISIONS.md` (OQ-03) |
| Bedrock model access enabled | Enable in the Bedrock console (Model access), then run §2 check | Converse returns text |
| Python 3.11+ | `python3 --version` | ≥ 3.11 |
| Decider runs locally | `strands-decider ask StrandsAgents/strands-decider-2B-hobson-v21 --state "test" --choice "Pick one?=a,b"` | Prints a choice with confidence |

## 2. One-time account checks

```bash
export AWS_PROFILE=<sso-profile>
export AWS_REGION=<region>

# Identity
aws sts get-caller-identity

# Find the model ID (text models)
aws bedrock list-foundation-models --by-output-modality TEXT \
  --query "modelSummaries[].modelId" --output table

# If the model requires an inference profile, list profiles
aws bedrock list-inference-profiles --query "inferenceProfileSummaries[].inferenceProfileId" --output table

# One-shot test (must succeed before Phase 4)
aws bedrock-runtime converse --model-id <model-id> \
  --messages '[{"role":"user","content":[{"text":"Reply with OK"}]}]' \
  --inference-config '{"maxTokens":10,"temperature":0}'
```

**Pass:** the converse call returns a message containing `OK`. **Fail:** `AccessDeniedException` → enable model access; `ValidationException` about on-demand throughput → use an inference-profile ID instead.

Record the model ID and the ARN(s) the runner role needs:
- Foundation model: `arn:aws:bedrock:<region>::foundation-model/<model-id>`
- Inference profile: `arn:aws:bedrock:<region>:<account-id>:inference-profile/<profile-id>` **plus** the foundation-model ARN in every region the profile routes to.

## 3. CloudFormation template (`infra/template.yaml`)

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: DLQ Judge hackathon resources. Synthetic data only.

Parameters:
  BedrockResourceArns:
    Type: CommaDelimitedList
    Description: Bedrock foundation-model and inference-profile ARNs the runner may invoke

Resources:
  DeadLetterQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: dlqj-orders-dlq
      MessageRetentionPeriod: 1209600        # 14 days
      SqsManagedSseEnabled: true

  SourceQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: dlqj-orders
      VisibilityTimeout: 30
      MessageRetentionPeriod: 345600         # 4 days
      SqsManagedSseEnabled: true
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt DeadLetterQueue.Arn
        maxReceiveCount: 3

  QuarantineBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub dlqj-quarantine-${AWS::AccountId}
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      LifecycleConfiguration:
        Rules:
          - Id: expire-after-7-days
            Status: Enabled
            ExpirationInDays: 7

  QuarantineBucketPolicy:
    Type: AWS::S3::BucketPolicy
    Properties:
      Bucket: !Ref QuarantineBucket
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Sid: DenyInsecureTransport
            Effect: Deny
            Principal: '*'
            Action: 's3:*'
            Resource:
              - !GetAtt QuarantineBucket.Arn
              - !Sub '${QuarantineBucket.Arn}/*'
            Condition:
              Bool:
                aws:SecureTransport: 'false'

  RunnerRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: dlqj-runner
      MaxSessionDuration: 3600
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS: !Sub arn:aws:iam::${AWS::AccountId}:root
            Action: sts:AssumeRole
      Policies:
        - PolicyName: dlqj-runner-policy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: DlqAccess
                Effect: Allow
                Action:
                  - sqs:ReceiveMessage
                  - sqs:DeleteMessage
                  - sqs:ChangeMessageVisibility
                  - sqs:GetQueueAttributes
                  - sqs:GetQueueUrl
                  - sqs:SendMessage
                Resource: !GetAtt DeadLetterQueue.Arn
              - Sid: SourceSend
                Effect: Allow
                Action:
                  - sqs:SendMessage
                  - sqs:GetQueueAttributes
                  - sqs:GetQueueUrl
                Resource: !GetAtt SourceQueue.Arn
              - Sid: BucketWrite
                Effect: Allow
                Action: s3:PutObject
                Resource:
                  - !Sub '${QuarantineBucket.Arn}/backup/*'
                  - !Sub '${QuarantineBucket.Arn}/quarantine/*'
              - Sid: BucketRestore
                Effect: Allow
                Action: s3:GetObject
                Resource: !Sub '${QuarantineBucket.Arn}/backup/*'
              - Sid: BucketList
                Effect: Allow
                Action: s3:ListBucket
                Resource: !GetAtt QuarantineBucket.Arn
                Condition:
                  StringLike:
                    s3:prefix: 'backup/*'
              - Sid: Bedrock
                Effect: Allow
                Action: bedrock:InvokeModel
                Resource: !Ref BedrockResourceArns
              - Sid: StackRead
                Effect: Allow
                Action: cloudformation:DescribeStacks
                Resource: !Sub arn:aws:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/${AWS::StackName}/*

Outputs:
  SourceQueueUrl:
    Value: !Ref SourceQueue
  DeadLetterQueueUrl:
    Value: !Ref DeadLetterQueue
  QuarantineBucketName:
    Value: !Ref QuarantineBucket
  RunnerRoleArn:
    Value: !GetAtt RunnerRole.Arn
```

No log group, Lambda, VPC, NAT or KMS customer-managed key is created.

## 4. Budget alert (once per account)

`infra/budget.json`:

```json
{"BudgetName":"dlq-judge","BudgetLimit":{"Amount":"10","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}
```

`infra/budget-notify.json` (replace the email locally; do not commit a real address):

```json
[{"Notification":{"NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN","Threshold":50,"ThresholdType":"PERCENTAGE"},
  "Subscribers":[{"SubscriptionType":"EMAIL","Address":"<your-email>"}]}]
```

```bash
aws budgets create-budget --account-id <account-id> \
  --budget file://infra/budget.json \
  --notifications-with-subscribers file://infra/budget-notify.json
```

**Pass:** `aws budgets describe-budget --account-id <account-id> --budget-name dlq-judge` returns the budget.

## 5. Deploy

```bash
export AWS_PROFILE=<sso-profile>
export AWS_REGION=<region>

aws cloudformation validate-template --template-body file://infra/template.yaml

aws cloudformation deploy \
  --stack-name dlq-judge \
  --template-file infra/template.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides BedrockResourceArns="<arn1>,<arn2>" \
  --tags project=dlq-judge

aws cloudformation describe-stacks --stack-name dlq-judge \
  --query "Stacks[0].{Status:StackStatus,Outputs:Outputs}" --output json
```

**Pass:** status `CREATE_COMPLETE` (or `UPDATE_COMPLETE`) and four outputs present.

### 5.1 Configure the runner profile

Add to `~/.aws/config` (see `SECURITY.md §2`):

```ini
[profile dlqj]
role_arn = <RunnerRoleArn output>
source_profile = <sso-profile>
region = <region>
```

```bash
aws sts get-caller-identity --profile dlqj     # Arn contains assumed-role/dlqj-runner
```

### 5.2 Local environment

```bash
cp .env.example .env      # then edit
# .env
AWS_PROFILE=dlqj
DLQJ_REGION=<region>
DLQJ_BEDROCK_MODEL_ID=<model-id or inference-profile-id>
```

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
strands-decider serve StrandsAgents/strands-decider-2B-hobson-v21 --port 8000   # separate terminal
dlq-judge doctor
```

**Pass:** `doctor` prints `PASS` for: config, identity (`dlqj-runner`), stack outputs, DLQ access, source queue access, bucket, Decider, Bedrock.

## 6. Verification commands

```bash
# Queue depth (DLQ)
aws sqs get-queue-attributes --profile dlqj \
  --queue-url <DeadLetterQueueUrl> \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible

# Source queue depth after apply
aws sqs get-queue-attributes --profile dlqj \
  --queue-url <SourceQueueUrl> --attribute-names ApproximateNumberOfMessages

# Quarantine and backup objects for a run
aws s3 ls s3://<bucket>/quarantine/<run_id>/ --profile <sso-profile>   # runner role cannot list quarantine/
aws s3 ls s3://<bucket>/backup/<run_id>/ --profile dlqj

# Bucket security settings (admin profile)
aws s3api get-public-access-block --bucket <bucket>
aws s3api get-bucket-encryption --bucket <bucket>
aws s3api get-bucket-policy --bucket <bucket>
```

Note: listing `quarantine/` uses your SSO profile, because the runner role may only list `backup/`.

## 7. Seed, triage, apply

```bash
dlq-judge seed --count 300 --seed 42           # sends synthetic messages to the DLQ
dlq-judge triage                               # dry run; prints run_id
dlq-judge ui --run <run_id>                    # review at http://127.0.0.1:8765 (Apply disabled server-side)
dlq-judge ui --run <run_id> --allow-apply      # only when you intend to apply from the UI
dlq-judge apply --run <run_id> --yes           # or apply from the CLI
```

**Pass after apply:** counts in `summary.json` `status_counts.applied` equal the number of messages that left the DLQ (escalated ones stay), and S3 has one backup object per non-escalated message.

## 8. Monitoring

v1.0 uses no CloudWatch resources. Observability comes from:
- run files in `runs/<run_id>/` (decisions, summary, clusters, restore log);
- the queue-depth commands in §6;
- the AWS Budgets alert (§4).

## 9. Rollback

| Situation | Steps |
|---|---|
| Stack create fails | CloudFormation rolls back automatically. Inspect: `aws cloudformation describe-stack-events --stack-name dlq-judge --max-items 20`. If status is `ROLLBACK_COMPLETE`: `aws cloudformation delete-stack --stack-name dlq-judge && aws cloudformation wait stack-delete-complete --stack-name dlq-judge`, fix, redeploy |
| Stack update fails | Automatic rollback to the previous template. If stuck in `UPDATE_ROLLBACK_FAILED`: `aws cloudformation continue-update-rollback --stack-name dlq-judge` |
| Bad template change already deployed | `git checkout <last-good-tag> -- infra/template.yaml` and run §5 deploy again |
| Bad application release | `git checkout <last-good-tag>` → `pip install -e ".[dev]"` → `dlq-judge doctor` |
| Messages changed by mistake | `dlq-judge restore --run <run_id>` (dry run) → `--apply --yes` (`SECURITY.md §4`) |
| Full reset for a fresh demo | §10 teardown → §5 deploy → §7 seed |

## 10. Teardown

```bash
AWS_PROFILE=<sso-profile> dlq-judge teardown   # prompts you to type the stack name; the runner role cannot delete
```

Equivalent manual commands (SSO profile):

```bash
aws s3 rm s3://dlqj-quarantine-<account-id> --recursive
aws cloudformation delete-stack --stack-name dlq-judge
aws cloudformation wait stack-delete-complete --stack-name dlq-judge
```

**Pass (TC-I10):**

```bash
aws sqs list-queues --queue-name-prefix dlqj            # no QueueUrls
aws s3api head-bucket --bucket dlqj-quarantine-<account-id>   # 404 / Not Found
aws cloudformation describe-stacks --stack-name dlq-judge     # "does not exist"
```

Keep the budget; delete it only when the project is finished: `aws budgets delete-budget --account-id <account-id> --budget-name dlq-judge`.

## 11. Cost notes

Cost drivers: SQS requests (a few thousand per run), S3 PUT/GET and a few MB of storage for ≤ 7 days, Bedrock input/output tokens (second opinions + ≤ 5 cluster calls per run; approach B in the benchmark is the largest single use). No always-on compute. Check current prices on the AWS pricing pages for SQS, S3 and Bedrock in your region before quoting any figure; record the estimate per 1,000 messages in `bench/results/results.md`.

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `AccessDenied` on `sts assume-role` | SSO identity lacks `sts:AssumeRole` | Use an admin permission set, or add the permission |
| `AccessDeniedException` from Bedrock | Model ARN not in `BedrockResourceArns`, or access not enabled | Redeploy with correct ARNs; enable access |
| Messages "missing" after a dry run | Visibility timeout 300 s still running | Wait 5 minutes or check `ApproximateNumberOfMessagesNotVisible` |
| Apply marks many messages `skipped / not_found` | Another process or a recent receive is holding them | Wait for visibility timeout, re-run apply (idempotent) |
| Bucket name already exists | Name collision (rare) | Delete leftover bucket or change the name pattern and record a decision |
