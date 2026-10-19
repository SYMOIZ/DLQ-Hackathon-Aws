# Spike notes (Phase 0)

Hardware: **AMD Ryzen 5 7430U with Radeon Graphics**, **15 GB RAM**. Device for Decider: `cpu`.

## P0-T3 — Decider server

| Item | Result |
|---|---|
| CLI | `strands-decider serve StrandsAgents/strands-decider-2B-hobson-v21 --host 127.0.0.1 --port 8000 --device cpu` |
| Bind | **127.0.0.1:8000** |
| Endpoint | `POST /v1/systemone` |
| Request shape | `questions` is a **dict** of named questions; choice uses `instructions` + `criteria` map (not `options` list) |
| Confidence | Returned on choice answers |
| Fixtures | `tests/fixtures/decider_request.json`, `decider_response.json` |
| Sample latency | ~5.4 s / call on CPU (single TimeoutError probe) |
| Health | `/health` reports `strands-decider-2B-hobson-v21`, base `Qwen/Qwen3.5-2B-Base` |

## P0-T4 — Strands InterventionHandler

See D-008. Import paths exercised in `scripts/spike_strands_handler.py` / `patterns/.../hook.py`.

## P0-T5 — Bedrock

Model: **`amazon.nova-micro-v1:0`** (cheapest that passed TC-I03/I04). Region `us-east-1`, profile `dlqj`.
