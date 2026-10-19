import json
import re
import secrets
import ssl
import urllib.request

import boto3

BASE = "https://<CLOUDFRONT_DOMAIN>"
ctx = ssl.create_default_context()
html = urllib.request.urlopen(BASE + "/", context=ctx).read().decode()
token = re.search(r'data-token="([^"]+)"', html).group(1)
c = boto3.Session(profile_name="default", region_name="us-east-1").client("cognito-idp")
email = f"e2e.{secrets.token_hex(2)}@example.com"
pw = "<TEST_PASSWORD>"
c.sign_up(
    ClientId="<COGNITO_CLIENT_ID>",
    Username=email,
    Password=pw,
    UserAttributes=[{"Name": "email", "Value": email}],
)
c.admin_confirm_sign_up(UserPoolId="<COGNITO_USER_POOL_ID>", Username=email)
req = urllib.request.Request(
    BASE + "/api/auth/login",
    data=json.dumps({"email": email, "password": pw}).encode(),
    headers={"Content-Type": "application/json", "X-DLQJ-Token": token},
    method="POST",
)
tok = json.loads(urllib.request.urlopen(req, context=ctx).read())["id_token"]
h = {"X-DLQJ-Token": token, "Authorization": "Bearer " + tok}
run = json.loads(
    urllib.request.urlopen(urllib.request.Request(BASE + "/api/run", headers=h), context=ctx).read()
)
print("run", run.get("run_id"), "processed", run.get("processed"), "queue", run.get("queue"))
msgs = json.loads(
    urllib.request.urlopen(
        urllib.request.Request(BASE + "/api/messages", headers=h), context=ctx
    ).read()
)
print("messages_total", msgs.get("total"), "items", len(msgs.get("items") or []))
