#!/usr/bin/env bash
# Push main via Git Bash only (no gh CLI). Never stages secrets.
set -euo pipefail
cd "/c/Users/symoi/Desktop/AWS weekly/DLQ-Hackathon -Aws"

REPO_URL="${REPO_URL:-https://github.com/SYMOIZ/DLQ-Hackathon-Aws.git}"

# Refuse to stage known secret / local-deploy artifacts
git rm -r --cached --ignore-unmatch \
  outputs.json outputs.env _qa_creds.txt \
  ssm-*.json ssm-*.txt dec.txt diag.txt diag2.txt jobout.txt \
  gh-auth-err.txt gh-auth-out.txt _gitbash_out.txt 2>/dev/null || true

if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "$REPO_URL"
else
  git remote set-url origin "$REPO_URL"
fi

git branch -M main

echo "Remote: $(git remote get-url origin)"
echo "HEAD:   $(git log -1 --oneline)"

if ! git ls-remote origin HEAD >/dev/null 2>&1; then
  echo "NO_REMOTE: create empty https://github.com/SYMOIZ/DLQ-Hackathon-Aws (no README), then re-run."
  exit 2
fi

git push -u origin main
echo "OK: https://github.com/SYMOIZ/DLQ-Hackathon-Aws"
