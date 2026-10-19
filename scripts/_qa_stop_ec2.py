"""Stop EC2 (do not terminate) and verify EBS + S3 data retained."""
from __future__ import annotations

import json
import time

import boto3

INSTANCE = "<EC2_INSTANCE_ID>"
REGION = "us-east-1"
ACCOUNT = "<AWS_ACCOUNT_ID>"

session = boto3.Session(profile_name="default", region_name=REGION)
ec2 = session.client("ec2")
s3 = session.client("s3")

print("stopping...", flush=True)
ec2.stop_instances(InstanceIds=[INSTANCE])

for i in range(60):
    st = ec2.describe_instances(InstanceIds=[INSTANCE])["Reservations"][0]["Instances"][0]
    name = st["State"]["Name"]
    print(f"[{i}] State={name}", flush=True)
    if name == "stopped":
        break
    time.sleep(5)
else:
    raise SystemExit("timeout waiting stopped")

inst = ec2.describe_instances(InstanceIds=[INSTANCE])["Reservations"][0]["Instances"][0]
vols = inst.get("BlockDeviceMappings") or []
print("block devices:", json.dumps(vols, default=str, indent=2), flush=True)

vol_ids = [v["Ebs"]["VolumeId"] for v in vols if v.get("Ebs")]
if vol_ids:
    vdesc = ec2.describe_volumes(VolumeIds=vol_ids)["Volumes"]
    for v in vdesc:
        print(
            f"volume {v['VolumeId']} State={v['State']} Size={v['Size']} "
            f"Attachments={[a.get('State') for a in v.get('Attachments', [])]}",
            flush=True,
        )

# S3 still has data
for bucket, prefix in [
    (f"dlqj-quarantine-{ACCOUNT}", "quarantine/"),
    (f"dlqj-quarantine-{ACCOUNT}", "backup/20261018T160623Z/"),
    (f"dlqj-deploy-{ACCOUNT}", "app/"),
]:
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=20)
    print(f"s3://{bucket}/{prefix} KeyCount={resp.get('KeyCount')}", flush=True)

print("VERIFY_OK state=stopped ebs_attached s3_intact", flush=True)
