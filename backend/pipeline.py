"""ATLAS V1 Pipeline Orchestrator.

Runs the three V1 agents in sequence:
  1. rs_analyzer   — equity quadrant classification + transitions
  2. sector_analyst — sector quadrant classification + rotations + divergences
  3. decisions_generator — finding-to-decision mapping

Usage:
    python -m atlas.pipeline run [--data-as-of YYYY-MM-DD]

The pipeline is idempotent: re-running with the same data_as_of produces
no new records (agents handle this via ON CONFLICT / check-before-insert).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents import decisions_generator, rs_analyzer, sector_analyst
from backend.clients.jip_data_service import JIPDataService
from backend.db.session import async_session_factory

log = structlog.get_logger(__name__)

PIPELINE_VERSION = "v1"

# IST offset — used when building a tz-aware date from a bare date
IST = timezone(timedelta(hours=5, minutes=30))


async def _get_latest_data_date(db: AsyncSession) -> datetime:
    """Query MAX(date) from de_rs_scores to find the most recent data date.

    Falls back to today IST if the query fails or returns NULL.
    Returns an IST-aware datetime at midnight.
    """
    try:
        rows = await db.execute(text("SELECT MAX(date) FROM de_rs_scores"))
        max_date = rows.scalar_one_or_none()
        if max_date is not None:
            # asyncpg returns datetime.date; convert to IST midnight datetime
            return datetime(max_date.year, max_date.month, max_date.day, 0, 0, 0, tzinfo=IST)
    except Exception as exc:
        log.warning("latest_data_date_query_failed", error=str(exc))

    # Fallback: today IST midnight
    today = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    log.info("latest_data_date_fallback", fallback_date=str(today))
    return today


async def _run_agent(
    agent_id: str,
    coro: Any,
    agent_results: dict[str, Any],
    agent_errors: dict[str, str],
) -> None:
    """Run a single agent coroutine, capturing stats or errors.

    Mutates agent_results on success, agent_errors on failure.
    """
    t0 = time.monotonic()
    try:
        stats = await coro
        duration_ms = int((time.monotonic() - t0) * 1000)
        agent_results[agent_id] = stats
        log.info(
            "agent_complete",
            agent_id=agent_id.replace("_", "-"),
            duration_ms=duration_ms,
            rows_read=stats.get("analyzed") or stats.get("findings_read", 0),
            findings_written=stats.get("findings_written", 0),
            decisions_written=stats.get("decisions_written", 0),
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        agent_errors[agent_id] = str(exc)
        log.error(
            "agent_failed",
            agent_id=agent_id.replace("_", "-"),
            duration_ms=duration_ms,
            error=str(exc),
        )


async def run_pipeline(
    data_as_of: Optional[datetime] = None,
) -> dict[str, Any]:
    """Run the full V1 pipeline.

    Args:
        data_as_of: IST-aware datetime for the pipeline run.
                    If None, queries MAX(date) from de_rs_scores.

    Returns:
        Summary dict with per-agent stats and totals.
    """
    pipeline_start = time.monotonic()

    async with async_session_factory() as db:
        if data_as_of is None:
            data_as_of = await _get_latest_data_date(db)
        elif data_as_of.tzinfo is None:
            raise ValueError("data_as_of must be timezone-aware (IST)")

        log.info(
            "pipeline_start",
            pipeline_version=PIPELINE_VERSION,
            data_as_of=str(data_as_of),
        )

        jip = JIPDataService(db)
        agent_results: dict[str, Any] = {}
        agent_errors: dict[str, str] = {}

        await _run_agent(
            "rs_analyzer",
            rs_analyzer.run(db, jip, data_as_of),
            agent_results,
            agent_errors,
        )
        await _run_agent(
            "sector_analyst",
            sector_analyst.run(db, jip, data_as_of),
            agent_results,
            agent_errors,
        )
        await _run_agent(
            "decisions_generator",
            decisions_generator.run(db, data_as_of),
            agent_results,
            agent_errors,
        )

    total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
    rs_stats = agent_results.get("rs_analyzer", {})
    sector_stats = agent_results.get("sector_analyst", {})
    dec_stats = agent_results.get("decisions_generator", {})

    total_findings = rs_stats.get("findings_written", 0) + sector_stats.get("findings_written", 0)
    total_decisions = dec_stats.get("decisions_written", 0)

    summary = {
        "pipeline_version": PIPELINE_VERSION,
        "data_as_of": str(data_as_of),
        "total_duration_ms": total_duration_ms,
        "total_findings": total_findings,
        "total_decisions": total_decisions,
        "agents": agent_results,
        "errors": agent_errors,
        "success": len(agent_errors) == 0,
    }

    log.info(
        "pipeline_complete",
        pipeline_version=PIPELINE_VERSION,
        data_as_of=str(data_as_of),
        total_duration_ms=total_duration_ms,
        total_findings=total_findings,
        total_decisions=total_decisions,
        agents_failed=len(agent_errors),
    )

    return summary
