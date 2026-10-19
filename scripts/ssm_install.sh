#!/bin/bash
set -euxo pipefail
DEPLOY_BUCKET=dlqj-deploy-<AWS_ACCOUNT_ID>
CF_HOST=<CLOUDFRONT_DOMAIN>
POOL=<COGNITO_USER_POOL_ID>
CLIENT=<COGNITO_CLIENT_ID>
BUCKET=dlqj-quarantine-<AWS_ACCOUNT_ID>
REGION=us-east-1
ACCOUNT=<AWS_ACCOUNT_ID>

dnf -y install python3.11 python3.11-pip git tar gzip || dnf -y install python3 python3-pip tar gzip
mkdir -p /opt/dlq-judge/runs
cd /opt/dlq-judge
aws s3 cp "s3://${DEPLOY_BUCKET}/app/dlq-judge-app.tgz" /tmp/dlq-judge-app.tgz --region "$REGION"
tar -xzf /tmp/dlq-judge-app.tgz -C /opt/dlq-judge
python3.11 -m venv /opt/dlq-judge/.venv || python3 -m venv /opt/dlq-judge/.venv
/opt/dlq-judge/.venv/bin/pip install -U pip wheel
/opt/dlq-judge/.venv/bin/pip install -e /opt/dlq-judge

cat >/etc/dlqj.env <<EOF
AWS_DEFAULT_REGION=${REGION}
DLQJ_REGION=${REGION}
DLQJ_ACCOUNT_ID=${ACCOUNT}
DLQJ_BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
DLQJ_BUCKET=${BUCKET}
DLQJ_COGNITO_USER_POOL_ID=${POOL}
DLQJ_COGNITO_CLIENT_ID=${CLIENT}
DLQJ_PUBLIC_HOST=${CF_HOST}
DLQJ_DECIDER_URL=http://127.0.0.1:8000
DLQJ_DECIDER_TIMEOUT_S=180
DLQJ_RUNS_DIR=/opt/dlq-judge/runs
DLQJ_UI_PORT=8765
DLQJ_BIND=0.0.0.0
DLQJ_ALLOW_APPLY=1
DLQJ_STACK_NAME=dlq-judge
HF_HOME=/opt/dlq-judge/.hf
TRANSFORMERS_CACHE=/opt/dlq-judge/.hf
EOF

cat >/etc/systemd/system/dlqj-decider.service <<'UNIT'
[Unit]
Description=DLQ Judge Decider
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/dlqj.env
WorkingDirectory=/opt/dlq-judge
ExecStart=/opt/dlq-judge/.venv/bin/strands-decider serve StrandsAgents/strands-decider-2B-hobson-v21 --host 127.0.0.1 --port 8000 --device cpu
Restart=always
RestartSec=15
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/dlqj-ui.service <<'UNIT'
[Unit]
Description=DLQ Judge UI
After=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/dlqj.env
WorkingDirectory=/opt/dlq-judge
ExecStart=/opt/dlq-judge/.venv/bin/python -m dlq_judge.serve_public
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable dlqj-decider dlqj-ui
systemctl restart dlqj-ui
systemctl restart dlqj-decider || true
systemctl is-active dlqj-ui
curl -sS -m 3 http://127.0.0.1:8765/healthz || true
echo INSTALL_OK
