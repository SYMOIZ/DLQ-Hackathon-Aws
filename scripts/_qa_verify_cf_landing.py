"""Verify CloudFront serves site landing + public stats."""
from __future__ import annotations

import urllib.request

BASE = "https://<CLOUDFRONT_DOMAIN>"


def main() -> None:
    html = urllib.request.urlopen(f"{BASE}/", timeout=45).read().decode("utf-8", "replace")
    land = html.find('id="site-landing"')
    auth = html.find('id="auth-gate"')
    checks = [
        ("site-landing present", land >= 0),
        ("site-landing before auth-gate", land >= 0 and land < auth),
        ("auth-gate hidden by default", "auth-gate dj hidden" in html),
        ("Server role", "Server role" in html),
        ("no Connected AWS account title", "Connected AWS account" not in html),
        ("Deploy AWS account", "Deploy AWS account (shared)" in html),
        ("cta subtitle", "Sign up to use the shared deploy account" in html),
        ("hero signup", "hero-signup" in html),
    ]
    stats = (
        urllib.request.urlopen(f"{BASE}/api/public/stats", timeout=45)
        .read()
        .decode("utf-8", "replace")
    )
    checks.append(
        (
            "payments stats",
            "dlqj-payments-dlq" in stats and '"processed": 50' in stats,
        )
    )
    failed = 0
    for name, ok in checks:
        print(("PASS" if ok else "FAIL"), name)
        if not ok:
            failed += 1
    print("stats", stats[:240])
    raise SystemExit(failed)


if __name__ == "__main__":
    main()
