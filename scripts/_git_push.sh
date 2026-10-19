#!/usr/bin/env bash
set -euo pipefail
cd "/c/Users/symoi/Desktop/AWS weekly/DLQ-Hackathon -Aws"

GH="/c/Program Files/GitHub CLI/gh.exe"
if [[ ! -x "$GH" ]]; then
  GH="$(command -v gh || true)"
fi

echo "== git status =="
git status -sb

echo "== stage =="
git add -A
git status -sb | head -80

echo "== commit if needed =="
if git diff --cached --quiet; then
  echo "nothing staged"
else
  git commit -m "$(cat <<'EOF'
Add AWS connector UI, Site landing, Cognito auto-confirm, and live QA docs.

Ship mockup-aligned Settings connectors, public landing, histogram fixes, and evidence-based QA reports for the deployed stack.
EOF
)"
fi

echo "== gh auth =="
"$GH" auth status || true

echo "== create repo + push =="
# Create public repo under logged-in user if remote missing
if ! git remote get-url origin >/dev/null 2>&1; then
  "$GH" repo create DLQ-Hackathon-Aws --public --source=. --remote=origin --description "DLQ Judge — SQS dead-letter triage on AWS (EC2 + CloudFront + Cognito)"
else
  echo "origin already set: $(git remote get-url origin)"
fi

git branch -M main
git push -u origin main

echo "== done =="
"$GH" repo view --web 2>/dev/null || "$GH" repo view
git remote -v
git status -sb
