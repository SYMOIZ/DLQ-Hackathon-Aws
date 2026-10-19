"""Poll CloudFront healthz until 200."""
from __future__ import annotations

import ssl
import time
import urllib.request

URL = "https://<CLOUDFRONT_DOMAIN>/healthz"
ctx = ssl.create_default_context()
for i in range(40):
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "dlqj-qa"})
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            body = resp.read()
            print(f"[{i}] {resp.status} {body[:120]!r}", flush=True)
            if resp.status == 200:
                raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as e:
        print(f"[{i}] err={e}", flush=True)
    time.sleep(5)
raise SystemExit("timeout")
