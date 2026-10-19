"""Layer 5: argparse entry point `dlq-judge`."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dlq_judge import __version__, aws_io, engine, runlog
from dlq_judge.config import get_config


def _cmd_doctor(_: argparse.Namespace) -> int:
    cfg = get_config()
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))

    add("env", bool(cfg.aws_profile and cfg.region and cfg.bedrock_model_id), "profile/region/model")
    try:
        ident = aws_io.session(cfg).client("sts").get_caller_identity()
        add("aws", True, f"arn={ident.get('Arn')}")
    except Exception as e:
        add("aws", False, str(e))
    try:
        d = aws_io.approx_depth(cfg, cfg.dlq)
        add("queues", True, f"{cfg.dlq} depth~{d}")
    except Exception as e:
        add("queues", False, str(e))
    try:
        if cfg.bucket:
            # Prefer list under known prefixes (HeadBucket may be denied by IAM).
            aws_io.session(cfg).client("s3").list_objects_v2(
                Bucket=cfg.bucket, Prefix="backup/", MaxKeys=1
            )
            add("bucket", True, cfg.bucket)
        else:
            add("bucket", False, "DLQJ_BUCKET unset")
    except Exception as e:
        add("bucket", False, str(e))
    try:
        if cfg.cognito_user_pool_id and cfg.cognito_client_id:
            # Lightweight check: IDs present + client can call Cognito (ListUsers truncated)
            client = aws_io.session(cfg).client("cognito-idp")
            client.list_users(UserPoolId=cfg.cognito_user_pool_id, Limit=1)
            add("cognito", True, cfg.cognito_user_pool_id)
        else:
            add("cognito", False, "Cognito IDs unset")
    except Exception as e:
        # Fall back to ID presence if ListUsers not permitted
        if cfg.cognito_user_pool_id and cfg.cognito_client_id:
            add("cognito", True, f"{cfg.cognito_user_pool_id} (ids set; {e})")
        else:
            add("cognito", False, str(e))
    try:
        url = cfg.decider_url.rstrip("/") + "/health"
        with urllib.request.urlopen(url, timeout=2) as r:
            add("decider", r.status == 200, cfg.decider_url)
    except Exception:
        # try /v1/systemone OPTIONS-less: just TCP
        try:
            with urllib.request.urlopen(cfg.decider_url, timeout=2) as r:
                add("decider", True, cfg.decider_url)
        except Exception as e:
            add("decider", False, str(e))
    try:
        from dlq_judge.models import State
        from dlq_judge import bedrock_client

        st = State(
            message_id="doctor",
            source_queue=cfg.source_queue,
            receive_count=1,
            age_minutes=1,
            error_type="TimeoutError",
            error_text="doctor probe",
            has_idempotency_key=False,
            body_masked="{}",
        )
        br = bedrock_client.second_opinion(cfg, st, "escalate_human")
        add("bedrock", bool(br.get("valid") or br.get("choice")), cfg.bedrock_model_id)
    except Exception as e:
        add("bedrock", False, str(e))

    failed = 0
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status:4}  {name}: {detail}")
        if not ok:
            failed += 1
    return 1 if failed else 0


def _cmd_seed(ns: argparse.Namespace) -> int:
    cfg = get_config()
    path = Path(ns.dataset or "bench/dataset/messages.jsonl")
    if not path.is_file():
        print(f"dataset missing: {path}", file=sys.stderr)
        return 1
    depth = aws_io.approx_depth(cfg, cfg.dlq)
    if depth > 0 and not ns.force:
        print(f"refused: DLQ not empty (depth≈{depth}); use --force", file=sys.stderr)
        return 1
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if ns.count:
        lines = lines[: ns.count]
    sent = 0
    for ln in lines:
        obj = json.loads(ln)
        body = obj.get("body")
        if not isinstance(body, str):
            body = json.dumps(body)
        attrs = obj.get("attributes") or {}
        # ensure fixture_id attribute
        if "fixture_id" not in attrs and obj.get("fixture_id"):
            attrs = {**attrs, "fixture_id": obj["fixture_id"]}
        aws_io.send_message(cfg, cfg.dlq, body, attrs)
        sent += 1
    print(f"seeded {sent} messages into {cfg.dlq}")
    return 0


def _cmd_triage(ns: argparse.Namespace) -> int:
    cfg = get_config()
    if ns.apply and not ns.yes:
        print("triage --apply requires --yes", file=sys.stderr)
        return 1
    run_id = engine.triage(cfg, apply=bool(ns.apply and ns.yes))
    print(run_id)
    return 0


def _cmd_apply(ns: argparse.Namespace) -> int:
    cfg = get_config()
    if not ns.yes:
        print("apply requires --yes", file=sys.stderr)
        return 1
    result = engine.apply_run(cfg, ns.run, yes=True)
    print(json.dumps(result))
    return 0


def _cmd_restore(ns: argparse.Namespace) -> int:
    cfg = get_config()
    n = engine.restore(
        cfg, ns.run, ns.message, apply=bool(ns.apply), yes=bool(ns.yes)
    )
    mode = "applied" if ns.apply and ns.yes else "dry_run"
    print(f"restore {mode}: {n} message(s)")
    return 0


def _cmd_ui(ns: argparse.Namespace) -> int:
    from dlq_judge.ui_server import serve

    cfg = get_config()
    run_id = ns.run
    if not run_id:
        runs = sorted(cfg.runs_dir.glob("*"), reverse=True)
        if not runs:
            print("no runs found; pass --run", file=sys.stderr)
            return 1
        run_id = runs[0].name
    serve(cfg, run_id, allow_apply=bool(ns.allow_apply), port=ns.port or cfg.ui_port)
    return 0


def _cmd_agent(ns: argparse.Namespace) -> int:
    from dlq_judge.agent import run_agent

    cfg = get_config()
    return run_agent(cfg, prompt=ns.prompt or "List tools and refuse unsafe discard.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dlq-judge", description="DLQ Judge CLI")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="Environment and AWS checks")
    d.set_defaults(func=_cmd_doctor)

    s = sub.add_parser("seed", help="Seed synthetic messages into the DLQ")
    s.add_argument("--dataset", default="bench/dataset/messages.jsonl")
    s.add_argument("--count", type=int, default=None)
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=_cmd_seed)

    t = sub.add_parser("triage", help="Dry-run triage (default)")
    t.add_argument("--apply", action="store_true")
    t.add_argument("--yes", action="store_true")
    t.set_defaults(func=_cmd_triage)

    a = sub.add_parser("apply", help="Apply a prior dry-run")
    a.add_argument("--run", required=True)
    a.add_argument("--yes", action="store_true")
    a.set_defaults(func=_cmd_apply)

    r = sub.add_parser("restore", help="Restore backups to DLQ")
    r.add_argument("--run", required=True)
    r.add_argument("--message", default=None)
    r.add_argument("--apply", action="store_true")
    r.add_argument("--yes", action="store_true")
    r.set_defaults(func=_cmd_restore)

    u = sub.add_parser("ui", help="Serve local UI for a run")
    u.add_argument("--run", default=None)
    u.add_argument("--allow-apply", action="store_true")
    u.add_argument("--port", type=int, default=None)
    u.set_defaults(func=_cmd_ui)

    g = sub.add_parser("agent", help="Strands agent with recovery guard")
    g.add_argument("--prompt", default=None)
    g.set_defaults(func=_cmd_agent)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    ns = parser.parse_args(argv)
    code = ns.func(ns)
    raise SystemExit(code or 0)


if __name__ == "__main__":
    main()
