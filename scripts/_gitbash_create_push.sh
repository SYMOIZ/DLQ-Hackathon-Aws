#!/usr/bin/env bash
# Create SYMOIZ/dlq-judge (public) and push main — Git Bash + git credentials.
set -euo pipefail
cd "/c/Users/symoi/Desktop/AWS weekly/DLQ-Hackathon -Aws"
export PATH="/c/Program Files/GitHub CLI:$PATH"

git branch -M main
git remote set-url origin https://github.com/SYMOIZ/dlq-judge.git

# Pull HTTPS token from Git Credential Manager (do not echo it)
CRED="$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null || true)"
USER="$(printf '%s\n' "$CRED" | awk -F= '/^username=/{print $2; exit}')"
TOKEN="$(printf '%s\n' "$CRED" | awk -F= '/^password=/{print $2; exit}')"

if [[ -z "${TOKEN}" ]]; then
  echo "NO_GIT_CREDENTIAL: open Git Bash and run:"
  echo '  gh auth login'
  echo '  gh repo create dlq-judge --public --source=. --remote=origin --push --description "Triage SQS dead-letter queues with Strands Decider 2B + Amazon Bedrock"'
  exit 2
fi

# Prefer gh if we can auth with the token
if command -v gh >/dev/null 2>&1; then
  printf '%s' "$TOKEN" | gh auth login --with-token 2>/dev/null || true
  if gh auth status >/dev/null 2>&1; then
    gh repo create dlq-judge --public --source=. --remote=origin --push \
      --description "Triage SQS dead-letter queues with Strands Decider 2B + Amazon Bedrock" \
      || git push -u origin main
    gh repo edit SYMOIZ/dlq-judge \
      --add-topic strands-decider-2b --add-topic aws --add-topic amazon-bedrock \
      --add-topic sqs --add-topic dead-letter-queue --add-topic ai-agent || true
    echo "REPO_URL=https://github.com/SYMOIZ/dlq-judge"
    echo "PATTERN_URL=https://github.com/SYMOIZ/dlq-judge/tree/main/patterns/confidence-gated-action"
    exit 0
  fi
fi

# API create + git push with token (no token printed)
CODE="$(curl -sS -o /tmp/dlqj_create.json -w '%{http_code}' \
  -X POST -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${TOKEN}" \
  https://api.github.com/user/repos \
  -d '{"name":"dlq-judge","description":"Triage SQS dead-letter queues with Strands Decider 2B + Amazon Bedrock","private":false,"auto_init":false}')"

echo "create_http=$CODE"
if [[ "$CODE" != "201" && "$CODE" != "422" ]]; then
  echo "CREATE_FAILED (see /tmp/dlqj_create.json)"
  exit 3
fi

git push -u "https://${USER}:${TOKEN}@github.com/SYMOIZ/dlq-judge.git" main
git remote set-url origin https://github.com/SYMOIZ/dlq-judge.git

echo "REPO_URL=https://github.com/SYMOIZ/dlq-judge"
echo "PATTERN_URL=https://github.com/SYMOIZ/dlq-judge/tree/main/patterns/confidence-gated-action"
