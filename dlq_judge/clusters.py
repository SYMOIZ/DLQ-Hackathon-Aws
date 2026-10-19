"""Layer 3: quarantine clusters + Bedrock explanations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from dlq_judge import bedrock_client
from dlq_judge.config import Config
from dlq_judge.models import Action


def build_and_explain(cfg: Config, records: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("action") != Action.QUARANTINE_POISON.value:
            continue
        et = (r.get("state") or {}).get("error_type") or "unknown"
        by_type[et].append(r)

    ranked = sorted(by_type.items(), key=lambda kv: len(kv[1]), reverse=True)
    top = ranked[: cfg.max_clusters]
    total_q = sum(len(v) for _, v in ranked) or 1
    items = []
    bedrock_calls = 0
    for error_type, group in top:
        samples = group[:5]
        try:
            expl = bedrock_client.explain_cluster(cfg, error_type=error_type, samples=samples)
            bedrock_calls += 1
        except Exception as e:
            expl = {
                "root_cause": "",
                "suggested_fix": "",
                "claims": [],
                "unverified": True,
                "latency_ms": 0,
                "sample_ids": [s.get("message_id") for s in samples],
                "error": str(e),
            }
        items.append(
            {
                "error_type": error_type,
                "count": len(group),
                "pct_of_quarantined": round(100.0 * len(group) / total_q, 1),
                "sample_ids": [s.get("message_id") for s in samples],
                "sample_error_text": (samples[0].get("state") or {}).get("error_text"),
                "root_cause": expl.get("root_cause"),
                "suggested_fix": expl.get("suggested_fix"),
                "claims": expl.get("claims") or [],
                "unverified": expl.get("unverified", False),
            }
        )
    return {"schema_version": 1, "items": items, "bedrock_calls": bedrock_calls}
