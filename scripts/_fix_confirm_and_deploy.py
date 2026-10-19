"""Confirm UNCONFIRMED Cognito users, patch IAM, package+SSM redeploy UI."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGION = "us-east-1"
PROFILE = "default"
POOL = "<COGNITO_USER_POOL_ID>"
INSTANCE = "<EC2_INSTANCE_ID>"
BUCKET = "dlqj-deploy-<AWS_ACCOUNT_ID>"
ROLE = "dlqj-ec2"


def aws(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["aws", *args, "--profile", PROFILE, "--region", REGION]
    print("+", " ".join(cmd[:8]), "...")
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True, capture_output=True)


def py_boto_confirm() -> None:
    import boto3

    c = boto3.Session(profile_name=PROFILE, region_name=REGION).client("cognito-idp")
    n = 0
    for page in c.get_paginator("list_users").paginate(UserPoolId=POOL):
        for u in page.get("Users", []):
            if u.get("UserStatus") != "UNCONFIRMED":
                continue
            uname = u["Username"]
            email = next(
                (a["Value"] for a in u.get("Attributes", []) if a["Name"] == "email"),
                uname,
            )
            try:
                c.admin_confirm_sign_up(UserPoolId=POOL, Username=uname)
                print("confirmed", email)
                n += 1
            except Exception as e:
                print("fail", email, e)
    print("confirmed_count", n)


def patch_iam() -> None:
    import boto3

    iam = boto3.Session(profile_name=PROFILE, region_name=REGION).client("iam")
    names = iam.list_role_policies(RoleName=ROLE).get("PolicyNames") or []
    if not names:
        print("no inline policies on", ROLE)
        return
    name = names[0]
    doc = iam.get_role_policy(RoleName=ROLE, PolicyName=name)["PolicyDocument"]
    needed = {
        "cognito-idp:AdminConfirmSignUp",
        "cognito-idp:AdminDeleteUser",
        "cognito-idp:AdminGetUser",
        "cognito-idp:ResendConfirmationCode",
    }
    changed = False
    for stmt in doc.get("Statement", []):
        acts = stmt.get("Action")
        if isinstance(acts, str):
            acts = [acts]
        if not isinstance(acts, list):
            continue
        if any(a.startswith("cognito-idp:") for a in acts):
            for a in needed:
                if a not in acts:
                    acts.append(a)
                    changed = True
            stmt["Action"] = acts
    if changed:
        iam.put_role_policy(
            RoleName=ROLE, PolicyName=name, PolicyDocument=json.dumps(doc)
        )
        print("iam_updated", name)
    else:
        print("iam_ok", name)


def package_and_deploy() -> None:
    subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "package_app.ps1"),
        ],
        cwd=ROOT,
        check=True,
    )
    tgz = ROOT / "dist" / "dlq-judge-app.tgz"
    aws("s3", "cp", str(tgz), f"s3://{BUCKET}/app/dlq-judge-app.tgz")
    params = {
        "commands": [
            "set -e",
            f"aws s3 cp s3://{BUCKET}/app/dlq-judge-app.tgz /tmp/a.tgz --region {REGION}",
            "tar -xzf /tmp/a.tgz -C /opt/dlq-judge",
            "/opt/dlq-judge/.venv/bin/pip install -e /opt/dlq-judge -q",
            "systemctl restart dlqj-ui",
            "sleep 2",
            "systemctl is-active dlqj-ui",
            "curl -sS http://127.0.0.1:8765/healthz",
        ]
    }
    (ROOT / "ssm-redeploy.json").write_text(json.dumps(params), encoding="ascii")
    out = aws(
        "ssm",
        "send-command",
        "--instance-ids",
        INSTANCE,
        "--document-name",
        "AWS-RunShellScript",
        "--parameters",
        f"file://{ROOT / 'ssm-redeploy.json'}",
        "--query",
        "Command.CommandId",
        "--output",
        "text",
    )
    cid = (out.stdout or "").strip()
    print("ssm", cid)
    for _ in range(30):
        time.sleep(5)
        st = aws(
            "ssm",
            "get-command-invocation",
            "--command-id",
            cid,
            "--instance-id",
            INSTANCE,
            "--query",
            "[Status,StandardOutputContent,StandardErrorContent]",
            "--output",
            "json",
            check=False,
        )
        try:
            data = json.loads(st.stdout or "[]")
        except Exception:
            continue
        status = data[0] if data else ""
        print("status", status)
        if status in ("Success", "Failed", "Cancelled", "TimedOut"):
            print("stdout", (data[1] if len(data) > 1 else "")[:800])
            print("stderr", (data[2] if len(data) > 2 else "")[:400])
            if status != "Success":
                sys.exit(1)
            break
    else:
        sys.exit("ssm timeout")


def verify_live() -> None:
    import urllib.request

    url = "https://<CLOUDFRONT_DOMAIN>/"
    html = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")
    checks = [
        ("login-only", "login-only" in html),
        ("auth-gate", 'id="auth-gate"' in html),
        ("profile-menu", 'id="profile-menu"' in html),
        ("Settings nav", "Settings" in html),
        ("Delete profile", "Delete profile" in html),
        ("Verify tab", "tab-verify" in html),
    ]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL"), name)
    if not all(ok for _, ok in checks):
        sys.exit(2)


def main() -> None:
    print("=== confirm users ===")
    py_boto_confirm()
    print("=== patch iam ===")
    patch_iam()
    print("=== deploy ===")
    package_and_deploy()
    print("=== verify ===")
    time.sleep(3)
    verify_live()
    print("ALL_OK")


if __name__ == "__main__":
    main()
