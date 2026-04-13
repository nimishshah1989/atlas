"""CLI entry point for the ATLAS V1 pipeline.

Usage:
    python -m atlas.pipeline run
    python -m atlas.pipeline run --data-as-of 2026-04-13

Exit codes:
    0 — all agents succeeded
    1 — one or more agents failed, or fatal error

Logs are emitted via structlog (captured by journalctl when run as systemd unit).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import structlog

log = structlog.get_logger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m atlas.pipeline",
        description="ATLAS V1 Market Intelligence Pipeline Runner",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full V1 pipeline")
    run_parser.add_argument(
        "--data-as-of",
        metavar="YYYY-MM-DD",
        default=None,
        help=("Date to run the pipeline for (IST). Defaults to MAX(date) from de_rs_scores."),
    )

    return parser.parse_args(argv)


def _parse_data_as_of(date_str: str | None) -> datetime | None:
    """Parse YYYY-MM-DD string to an IST-aware midnight datetime.

    Returns None if date_str is None (pipeline will auto-detect latest date).
    Raises SystemExit(1) on bad format.
    """
    if date_str is None:
        return None
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
        return parsed.replace(tzinfo=IST)
    except ValueError:
        log.error("invalid_date_format", date_str=date_str, expected="YYYY-MM-DD")
        sys.exit(1)


async def _run(data_as_of: datetime | None) -> int:
    """Async wrapper — returns exit code."""
    # Import here (not at module level) to avoid side effects on import
    from backend.pipeline import run_pipeline

    try:
        summary = await run_pipeline(data_as_of=data_as_of)
    except Exception as exc:
        log.error("pipeline_fatal_error", error=str(exc))
        return 1

    if summary.get("success"):
        log.info(
            "pipeline_exit_success",
            data_as_of=summary.get("data_as_of"),
            total_duration_ms=summary.get("total_duration_ms"),
            total_findings=summary.get("total_findings"),
            total_decisions=summary.get("total_decisions"),
        )
        return 0
    else:
        errors = summary.get("errors", {})
        log.error(
            "pipeline_exit_partial_failure",
            failed_agents=list(errors.keys()),
            errors=errors,
        )
        return 1


def main(argv: list[str] | None = None) -> None:
    """Main entry point — parses args and runs pipeline."""
    args = _parse_args(argv)
    data_as_of = _parse_data_as_of(getattr(args, "data_as_of", None))
    exit_code = asyncio.run(_run(data_as_of))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
