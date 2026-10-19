"""Start EC2, wait running + SSM online + healthz 200."""
from __future__ import annotations

import json
import ssl
import time
import urllib.request

import boto3

INSTANCE = "<EC2_INSTANCE_ID>"
REGION = "us-east-1"
HEALTHZ = "https://<CLOUDFRONT_DOMAIN>/healthz"

session = boto3.Session(profile_name="default", region_name=REGION)
ec2 = session.client("ec2")
ssm = session.client("ssm")

print("starting...", flush=True)
ec2.start_instances(InstanceIds=[INSTANCE])

for i in range(60):
    st = ec2.describe_instances(InstanceIds=[INSTANCE])["Reservations"][0]["Instances"][0]
    name = st["State"]["Name"]
    ip = st.get("PublicIpAddress")
    print(f"[{i}] state={name} ip={ip}", flush=True)
    if name == "running":
        break
    time.sleep(5)
else:
    raise SystemExit("timeout waiting for running")

print("waiting SSM...", flush=True)
for i in range(60):
    try:
        info = ssm.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [INSTANCE]}]
        )["InstanceInformationList"]
        if info and info[0].get("PingStatus") == "Online":
            print(f"SSM online: {json.dumps(info[0], default=str)[:300]}", flush=True)
            break
    except Exception as e:
        print(f"ssm err: {e}", flush=True)
    time.sleep(5)
else:
    print("WARN: SSM not online yet, continuing for healthz", flush=True)

ctx = ssl.create_default_context()
print("waiting healthz...", flush=True)
for i in range(90):
    try:
        req = urllib.request.Request(HEALTHZ, headers={"User-Agent": "dlqj-qa"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            body = resp.read()
            print(f"[{i}] healthz={resp.status} {body[:120]!r}", flush=True)
            if resp.status == 200:
                print("READY", flush=True)
                raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as e:
        print(f"[{i}] healthz err: {e}", flush=True)
    time.sleep(5)

raise SystemExit("timeout healthz")
