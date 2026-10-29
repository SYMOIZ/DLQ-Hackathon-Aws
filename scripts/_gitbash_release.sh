#!/usr/bin/env bash
# Git Bash only: secret scan → clean main commit → create/push dlq-judge
set -euo pipefail
cd "/c/Users/symoi/Desktop/AWS weekly/DLQ-Hackathon -Aws"

export PATH="/c/Program Files/GitHub CLI:$PATH"
GH="$(command -v gh || true)"
PY=".venv/Scripts/python.exe"

echo "== secret scan (paths that would be committed) =="
HITS="$($PY - <<'PY'
import re, subprocess
from pathlib import Path
skip={".git",".venv","venv","__pycache__","runs","dist",".pytest_cache","node_modules","dlq_judge.egg-info"}
akia=re.compile(r"AKIA[0-9A-Z]{16}")
# Real secret material only (not boto3 kwarg names)
secret=re.compile(r"(AWS_SECRET_ACCESS_KEY|aws_secret_access_key)\s*=\s*['\"][A-Za-z0-9/+=]{20,}['\"]")
pwd=re.compile(r"(password|Password)\s*=\s*['\"](?!&lt;|<|TestPass|password|pw|PASSWORD)[^'\"]{4,}['\"]")
# Real deploy values come from the environment, never from this file:
#   DLQJ_FORBID_ACCOUNTS="<acct>[,<acct>]"  DLQJ_FORBID_PATTERN="<regex of live IDs>"
import os
forbid_acct={a for a in os.environ.get("DLQJ_FORBID_ACCOUNTS","").split(",") if a}
live=re.compile(os.environ.get("DLQJ_FORBID_PATTERN") or r"(?!)")
bad=[]
def ignored(path: Path) -> bool:
    r = subprocess.run(["git","check-ignore","-q",str(path)])
    return r.returncode == 0
for p in Path(".").rglob("*"):
    if not p.is_file() or any(x in skip for x in p.parts):
        continue
    if ignored(p):
        continue
    if p.suffix.lower() not in {".py",".js",".html",".md",".json",".yaml",".yml",".sh",".txt",".toml"}:
        continue
    if p.name.startswith(".env") and p.name != ".env.example":
        continue
    if p.name in {"_scrub_live_ids.py","_commit_and_push.sh","_gitbash_release.sh","_hackathon_prep.sh"}:
        continue
    try:
        t=p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    if akia.search(t):
        bad.append(f"{p}:AKIA"); continue
    if secret.search(t):
        bad.append(f"{p}:aws_secret"); continue
    if pwd.search(t):
        bad.append(f"{p}:password"); continue
    if live.search(t):
        bad.append(f"{p}:live_id"); continue
    for m in re.finditer(r"\b(\d{12})\b", t):
        if m.group(1) in forbid_acct:
            bad.append(f"{p}:account_id"); break
print("\n".join(bad))
PY
)"

if [[ -n "${HITS}" ]]; then
  echo "SECRET_SCAN_FAILED:"
  echo "$HITS"
  exit 1
fi
echo "secret scan clean"

echo "== switch to clean main =="
git checkout --orphan release-main 2>/dev/null || git checkout release-main
git reset
git add -A
# never stage local secrets / helpers
git reset HEAD -- \
  .env outputs.json outputs.env _qa_creds.txt \
  ssm-*.json ssm-*.txt dec.txt diag.txt diag2.txt jobout.txt \
  gh-auth-*.txt _gitbash_out.txt _jobs jobs.tgz \
  scripts/_scrub_live_ids.py scripts/_hackathon_prep.sh scripts/_run_prep_tests.sh \
  scripts/_commit_and_push.sh scripts/_gitbash_release.sh 2>/dev/null || true

echo "== staged secret scan =="
"$PY" - <<'PY'
import os, re, subprocess, sys
blob = subprocess.check_output(["git", "diff", "--cached"], text=True, errors="ignore")
checks = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA"),
    (re.compile(r"(AWS_SECRET_ACCESS_KEY|aws_secret_access_key)\s*=\s*['\"][A-Za-z0-9/+=]{20,}['\"]"), "aws_secret"),
    (re.compile(os.environ.get("DLQJ_FORBID_PATTERN") or r"(?!)"), "live_id"),
    *[(re.compile(rf"\b{re.escape(a)}\b"), "account_id")
      for a in os.environ.get("DLQJ_FORBID_ACCOUNTS", "").split(",") if a],
]
for rx, label in checks:
    if rx.search(blob):
        print(f"STAGED_SECRET:{label}")
        sys.exit(1)
print("staged clean")
PY

git commit -m "$(cat <<'EOF'
Initial commit: DLQ Judge

Hackathon-ready public snapshot: confidence-gated Decider pattern, agent/ui layout, Apache-2.0, secrets scrubbed.
EOF
)"

git branch -M main

# Point origin at dlq-judge
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin https://github.com/SYMOIZ/dlq-judge.git
else
  git remote add origin https://github.com/SYMOIZ/dlq-judge.git
fi

echo "== create + push =="
if [[ -n "$GH" ]] && "$GH" auth status >/dev/null 2>&1; then
  "$GH" repo create dlq-judge --public --source=. --remote=origin --push \
    --description "Triage SQS dead-letter queues with Strands Decider 2B + Amazon Bedrock" \
    || git push -u origin main
  "$GH" repo edit SYMOIZ/dlq-judge --add-topic strands-decider-2b --add-topic aws \
    --add-topic amazon-bedrock --add-topic sqs --add-topic dead-letter-queue --add-topic ai-agent || true
else
  echo "gh not authenticated; pushing with git credentials to https://github.com/SYMOIZ/dlq-judge.git"
  echo "If the repo does not exist yet, create it empty on GitHub named dlq-judge, then re-run push."
  git push -u origin main
fi

echo "REPO_URL=https://github.com/SYMOIZ/dlq-judge"
echo "PATTERN_URL=https://github.com/SYMOIZ/dlq-judge/tree/main/patterns/confidence-gated-action"
