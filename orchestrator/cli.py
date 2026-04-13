"""User-facing CLI for the ATLAS forge orchestrator.

Examples:
    python -m orchestrator.cli status
    python -m orchestrator.cli sync
    python -m orchestrator.cli run --once
    python -m orchestrator.cli run --all
    python -m orchestrator.cli run C5
    python -m orchestrator.cli unblock C7
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import state_machine as sm
from .logging_config import configure, get_logger
from .plan_loader import load_plan, sync_plan_to_state
from .runner import Runner
from .state import StateStore

DEFAULT_PLAN = Path(__file__).parent / "plan.yaml"
DEFAULT_DB = Path(__file__).parent / "state.db"
DEFAULT_LOG_DIR = Path(__file__).parent / "logs"


def cmd_status(args: argparse.Namespace) -> int:
    store = StateStore(args.db)
    chunks = store.list_chunks()
    if args.json:
        print(json.dumps(chunks, indent=2))
        return 0
    print(f"{'ID':<5} {'STATUS':<14} {'ATTEMPTS':<9} TITLE")
    print("-" * 80)
    for c in chunks:
        print(f"{c['id']:<5} {c['status']:<14} {c['attempts']:<9} {c['title']}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan)
    store = StateStore(args.db)
    final = sync_plan_to_state(plan, store)
    print(f"Synced {len(final)} chunks from {args.plan}")
    for cid, status in final.items():
        print(f"  {cid}: {status}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    log = get_logger()
    runner = Runner(args.plan, args.db, dry_run=args.dry_run)

    if args.chunk:
        log.info("running_specific_chunk", chunk=args.chunk)
        runner._run_chunk(args.chunk)  # noqa: SLF001 — explicit override
        return 0

    if args.all:
        completed = runner.run_all()
        log.info("run_all_complete", completed=completed)
        return 0

    cid = runner.run_one()
    if cid is None:
        print("no chunks ready to run")
        return 0
    log.info("run_one_complete", chunk=cid)
    return 0


def cmd_unblock(args: argparse.Namespace) -> int:
    store = StateStore(args.db)
    chunk = store.get_chunk(args.chunk)
    if chunk is None:
        print(f"unknown chunk: {args.chunk}", file=sys.stderr)
        return 1
    if chunk["status"] != sm.BLOCKED:
        print(
            f"chunk {args.chunk} is {chunk['status']}, not BLOCKED",
            file=sys.stderr,
        )
        return 1
    store.set_status(args.chunk, sm.PENDING, "manual unblock via CLI")
    print(f"{args.chunk} → PENDING")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = StateStore(args.db)
    chunk = store.get_chunk(args.chunk)
    if chunk is None:
        print(f"unknown chunk: {args.chunk}", file=sys.stderr)
        return 1
    qrun = store.latest_quality_run(args.chunk)
    print(json.dumps({"chunk": chunk, "latest_quality_run": qrun}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="forge")
    p.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    p.add_argument("--log-level", default="INFO")

    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("status", help="show all chunks")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("sync", help="sync plan.yaml into state DB")
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("run", help="run chunks")
    g = s.add_mutually_exclusive_group()
    g.add_argument(
        "--once",
        dest="all",
        action="store_false",
        default=False,
        help="run a single ready chunk (default)",
    )
    g.add_argument("--all", action="store_true", help="keep running until none are ready")
    s.add_argument("chunk", nargs="?", default=None, help="run a specific chunk by id")
    s.add_argument("--dry-run", action="store_true", help="don't actually spawn claude or score")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("unblock", help="move a BLOCKED chunk back to PENDING")
    s.add_argument("chunk")
    s.set_defaults(func=cmd_unblock)

    s = sub.add_parser("show", help="show chunk + latest quality run")
    s.add_argument("chunk")
    s.set_defaults(func=cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure(args.log_dir, level=args.log_level)
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
