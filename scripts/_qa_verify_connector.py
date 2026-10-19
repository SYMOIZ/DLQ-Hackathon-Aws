"""Verify AWS connector UI + API on CloudFront."""
from __future__ import annotations

import json
import re
import secrets
import ssl
import urllib.request

import boto3

BASE = "https://<CLOUDFRONT_DOMAIN>"
CLIENT = "<COGNITO_CLIENT_ID>"
POOL = "<COGNITO_USER_POOL_ID>"
ctx = ssl.create_default_context()


def main() -> None:
    html = urllib.request.urlopen(BASE + "/", context=ctx, timeout=45).read().decode()
    checks = {
        "btn-add-aws": "btn-add-aws" in html,
        "aws-connect-panel": "aws-connect-panel" in html,
        "site-landing": "site-landing" in html,
        "no_old_shared_copy": "Deploy AWS account (shared)" not in html,
    }
    for k, v in checks.items():
        print(("PASS" if v else "FAIL"), k)

    token = re.search(r'data-token="([^"]+)"', html).group(1)
    cognito = boto3.Session(profile_name="default", region_name="us-east-1").client(
        "cognito-idp"
    )
    email = f"conn.{secrets.token_hex(2)}@example.com"
    pw = "<TEST_PASSWORD>"
    cognito.sign_up(
        ClientId=CLIENT,
        Username=email,
        Password=pw,
        UserAttributes=[{"Name": "email", "Value": email}],
    )
    req = urllib.request.Request(
        BASE + "/api/auth/login",
        data=json.dumps({"email": email, "password": pw}).encode(),
        headers={"Content-Type": "application/json", "X-DLQJ-Token": token},
        method="POST",
    )
    tok = json.loads(urllib.request.urlopen(req, context=ctx, timeout=45).read())[
        "id_token"
    ]
    h = {"X-DLQJ-Token": token, "Authorization": "Bearer " + tok}
    conn = json.loads(
        urllib.request.urlopen(
            urllib.request.Request(BASE + "/api/aws/connector", headers=h),
            context=ctx,
            timeout=60,
        ).read()
    )
    print(
        "connector",
        conn.get("st_label"),
        conn.get("account_id"),
        "queues=",
        conn.get("queues"),
        conn.get("role_name"),
    )
    assert conn.get("account_id") == "<AWS_ACCOUNT_ID>"
    assert conn.get("st_label") in ("Connected", "Degraded")
    assert (conn.get("queues") or 0) >= 1
    print("PASS connector_api")

    test_req = urllib.request.Request(
        BASE + "/api/aws/connector/test",
        data=b"{}",
        headers={**h, "Content-Type": "application/json"},
        method="POST",
    )
    test = json.loads(
        urllib.request.urlopen(test_req, context=ctx, timeout=60).read()
    )
    print("test", test.get("ok"), (test.get("message") or "")[:120])
    assert test.get("ok") is True
    print("PASS connector_test")
    print("DONE")


if __name__ == "__main__":
    main()
