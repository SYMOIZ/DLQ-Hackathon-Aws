"""Check CloudFront origin vs current EC2 public DNS/IP; update if stale."""
from __future__ import annotations

import json
import time

import boto3

INSTANCE = "<EC2_INSTANCE_ID>"
REGION = "us-east-1"
DIST_HINT = "<CLOUDFRONT_DIST_ID>"

session = boto3.Session(profile_name="default", region_name=REGION)
ec2 = session.client("ec2")
cf = session.client("cloudfront")

inst = ec2.describe_instances(InstanceIds=[INSTANCE])["Reservations"][0]["Instances"][0]
public_ip = inst.get("PublicIpAddress")
public_dns = inst.get("PublicDnsName")
print(f"EC2 ip={public_ip} dns={public_dns}", flush=True)

dists = cf.list_distributions()["DistributionList"].get("Items", [])
dist = None
for d in dists:
    if DIST_HINT in d.get("DomainName", "") or DIST_HINT in d.get("Id", ""):
        dist = d
        break
    aliases = d.get("Aliases", {}).get("Items") or []
    if any(DIST_HINT in a for a in aliases):
        dist = d
        break
# match by domain name containing our CF domain
for d in dists:
    if d.get("DomainName", "").startswith(DIST_HINT):
        dist = d
        break

if not dist:
    print("distributions:", json.dumps([{k: d.get(k) for k in ('Id','DomainName','Status')} for d in dists], indent=2), flush=True)
    raise SystemExit("distribution not found")

dist_id = dist["Id"]
print(f"Found dist {dist_id} domain={dist['DomainName']}", flush=True)

cfg_resp = cf.get_distribution_config(Id=dist_id)
etag = cfg_resp["ETag"]
config = cfg_resp["DistributionConfig"]
origins = config["Origins"]["Items"]
print("origins before:", json.dumps(origins, default=str, indent=2), flush=True)

# Prefer DNS over IP for EC2
new_domain = public_dns or public_ip
if not new_domain:
    raise SystemExit("no public address")

changed = False
for o in origins:
    old = o.get("DomainName")
    if old != new_domain:
        print(f"updating origin {o.get('Id')}: {old} -> {new_domain}", flush=True)
        o["DomainName"] = new_domain
        # Custom origin settings for HTTP
        if "CustomOriginConfig" in o:
            o["CustomOriginConfig"]["HTTPPort"] = 8765
            o["CustomOriginConfig"]["OriginProtocolPolicy"] = "http-only"
        changed = True
    else:
        print(f"origin already {new_domain}", flush=True)

if changed:
    cf.update_distribution(DistributionConfig=config, Id=dist_id, IfMatch=etag)
    print("update_distribution submitted", flush=True)
    for i in range(60):
        d2 = cf.get_distribution(Id=dist_id)["Distribution"]
        status = d2["Status"]
        print(f"[{i}] Status={status}", flush=True)
        if status == "Deployed":
            break
        time.sleep(10)
else:
    print("no origin change needed", flush=True)

print("DONE", flush=True)
