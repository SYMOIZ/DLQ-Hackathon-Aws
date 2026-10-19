#!/bin/bash
set -euxo pipefail
exec > >(tee /var/log/dlqj-userdata.log) 2>&1

dnf -y update || true
dnf -y install python3.11 python3.11-pip git unzip || dnf -y install python3 python3-pip git unzip
mkdir -p /opt/dlq-judge /opt/dlq-judge/runs /opt/dlq-judge/models
cd /opt/dlq-judge

# Deploy package from S3 (uploaded by deploy script)
aws s3 cp "s3://${DEPLOY_BUCKET}/app/dlq-judge-app.tgz" /tmp/dlq-judge-app.tgz
tar -xzf /tmp/dlq-judge-app.tgz -C /opt/dlq-judge
python3.11 -m venv /opt/dlq-judge/.venv || python3 -m venv /opt/dlq-judge/.venv
/opt/dlq-judge/.venv/bin/pip install -U pip
/opt/dlq-judge/.venv/bin/pip install -e "/opt/dlq-judge[dev]"

# Optional: preseed HF weights from S3 if present
if aws s3 ls "s3://${DEPLOY_BUCKET}/models/qwen/" >/dev/null 2>&1; then
  mkdir -p /root/.cache/huggingface/hub
  aws s3 sync "s3://${DEPLOY_BUCKET}/models/" /root/.cache/huggingface/hub/ || true
fi

cat >/etc/dlqj.env <<EOF
AWS_DEFAULT_REGION=${AWS_REGION}
DLQJ_REGION=${AWS_REGION}
DLQJ_ACCOUNT_ID=${AWS_ACCOUNT}
DLQJ_BEDROCK_MODEL_ID=${BEDROCK_MODEL}
DLQJ_BUCKET=${QUARANTINE_BUCKET}
DLQJ_COGNITO_USER_POOL_ID=${COGNITO_POOL}
DLQJ_COGNITO_CLIENT_ID=${COGNITO_CLIENT}
DLQJ_PUBLIC_HOST=${PUBLIC_HOST}
DLQJ_DECIDER_URL=http://127.0.0.1:8000
DLQJ_DECIDER_TIMEOUT_S=120
DLQJ_RUNS_DIR=/opt/dlq-judge/runs
DLQJ_UI_PORT=8765
DLQJ_STACK_NAME=dlq-judge
EOF

cat >/etc/systemd/system/dlqj-decider.service <<'UNIT'
[Unit]
Description=DLQ Judge Strands Decider
After=network.target

[Service]
Type=simple
EnvironmentFile=/etc/dlqj.env
WorkingDirectory=/opt/dlq-judge
ExecStart=/opt/dlq-judge/.venv/bin/strands-decider serve StrandsAgents/strands-decider-2B-hobson-v21 --host 127.0.0.1 --port 8000 --device cpu
Restart=always
RestartSec=10
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/dlqj-ui.service <<'UNIT'
[Unit]
Description=DLQ Judge UI
After=network.target dlqj-decider.service
Wants=dlqj-decider.service

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
systemctl start dlqj-decider
# UI starts even if Decider still loading
systemctl start dlqj-ui
echo userdata_done
