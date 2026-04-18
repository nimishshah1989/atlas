"""Routine visibility service — reads jip-source-manifest.yaml and enriches
with live last-run data from de_routine_runs (graceful degradation if missing).

V11-0 spec: GET /api/v1/system/routines
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import structlog
import yaml
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.routines import RoutineEntry, RoutineLastRun, RoutinesResponse

log = structlog.get_logger()

IST = timezone(timedelta(hours=5, minutes=30))

# Resolved relative to repo root (this file lives at backend/services/)
_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "specs" / "jip-source-manifest.yaml"
)

# Module-level status tracking for transition logging
_prev_statuses: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def _load_manifest() -> dict[str, Any]:
    """Load and parse jip-source-manifest.yaml. Returns empty dict on failure."""
    try:
        raw = _MANIFEST_PATH.read_text(encoding="utf-8")
        parsed: Any = yaml.safe_load(raw)
        if not isinstance(parsed, dict):
            log.warning("routines_manifest_not_dict", path=str(_MANIFEST_PATH))
            return {}
        return parsed
    except FileNotFoundError:
        log.warning("routines_manifest_not_found", path=str(_MANIFEST_PATH))
        return {}
    except yaml.YAMLError as exc:
        log.warning("routines_manifest_parse_error", path=str(_MANIFEST_PATH), error=str(exc))
        return {}
    except OSError as exc:
        log.warning("routines_manifest_read_error", path=str(_MANIFEST_PATH), error=str(exc))
        return {}


def _parse_tables(table_val: Any) -> list[str]:
    """Handle both string 'de_a, de_b' and list forms from the manifest."""
    if table_val is None:
        return []
    if isinstance(table_val, list):
        # List of strings or dicts (new_routines columns field is list of dicts)
        return [str(t).strip() for t in table_val if isinstance(t, str) and t.strip()]
    if isinstance(table_val, str):
        return [t.strip() for t in table_val.split(",") if t.strip()]
    return []


# ---------------------------------------------------------------------------
# DB query
# ---------------------------------------------------------------------------


async def _query_last_runs(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Query de_routine_runs for the latest run per routine_id.

    Returns an empty dict on any failure (graceful degradation — missing
    table, wrong columns, or any other DB error).
    """
    sql = text("""
        SELECT DISTINCT ON (routine_id)
            routine_id,
            run_id::text,
            status,
            rows_fetched,
            rows_inserted,
            rows_updated,
            duration_ms,
            error_message,
            started_at
        FROM de_routine_runs
        ORDER BY routine_id, started_at DESC
    """)
    try:
        query_result = await session.execute(sql)
        rows = query_result.mappings().all()
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            rid = row["routine_id"]
            out[rid] = dict(row)
        return out
    except ProgrammingError as exc:
        log.warning("de_routine_runs_unavailable", error=str(exc))
        return {}
    except Exception as exc:  # noqa: BLE001
        log.warning("de_routine_runs_query_failed", error=str(exc))
        return {}


# ---------------------------------------------------------------------------
# SLA and display status computation
# ---------------------------------------------------------------------------


def _compute_sla_breached(
    sla_hours: Optional[int],
    ran_at: Optional[datetime],
) -> bool:
    """Return True if the SLA is breached.

    - If sla_hours is None: no SLA defined → never breached.
    - If ran_at is None and sla_hours is set: no run recorded → breach.
    - If now - ran_at > sla_hours * 1.1 (10% grace): breach.
    """
    if sla_hours is None:
        return False
    if ran_at is None:
        return True
    now = datetime.now(tz=timezone.utc)
    # Ensure ran_at is tz-aware for comparison
    ran_at_utc = ran_at if ran_at.tzinfo is not None else ran_at.replace(tzinfo=timezone.utc)
    grace_seconds = sla_hours * 3600 * 1.1
    elapsed = (now - ran_at_utc).total_seconds()
    return elapsed > grace_seconds


def _compute_display_status(
    manifest_status: str,
    is_new: bool,
    sla_breached: bool,
    last_run: Optional[RoutineLastRun],
) -> str:
    """Derive display_status from manifest state and live run data."""
    if is_new:
        return "planned"
    if sla_breached:
        return "sla_breached"
    if last_run is None:
        if manifest_status == "live":
            return "missing"
        return manifest_status if manifest_status else "unknown"
    run_status = last_run.status
    if run_status == "success":
        return "live"
    if run_status == "partial":
        return "partial"
    if run_status == "failed":
        return "missing"
    return manifest_status if manifest_status else "unknown"


# ---------------------------------------------------------------------------
# Status transition logging
# ---------------------------------------------------------------------------


def _maybe_log_transition(routine_id: str, display_status: str) -> None:
    """Emit a structured log if the routine's display_status has changed."""
    prev = _prev_statuses.get(routine_id)
    if prev is not None and prev != display_status:
        log.info(
            "routine_status_transition",
            routine_id=routine_id,
            from_status=prev,
            to_status=display_status,
        )
    _prev_statuses[routine_id] = display_status


# ---------------------------------------------------------------------------
# Main service function
# ---------------------------------------------------------------------------


async def get_routines(session: AsyncSession) -> RoutinesResponse:
    """Build RoutinesResponse from manifest + live DB data."""
    manifest = _load_manifest()

    existing_raw: list[Any] = manifest.get("existing", []) or []
    new_raw: list[Any] = manifest.get("new_routines", []) or []

    # Query live run data (graceful fail → empty dict)
    last_runs = await _query_last_runs(session)
    # data_available reflects whether de_routine_runs is reachable at all
    db_available = await _check_db_available(session)

    entries: list[RoutineEntry] = []

    # ---- existing routines ----
    for raw in existing_raw:
        if not isinstance(raw, dict):
            continue
        routine_id = str(raw.get("id", ""))
        table_val = raw.get("table", "")
        tables = _parse_tables(table_val)
        cadence = str(raw.get("cadence", ""))
        schedule = raw.get("schedule")
        source = raw.get("source")
        manifest_status = str(raw.get("status", "live"))
        sla_hours = raw.get("sla_freshness_hours")
        sla_hours_int: Optional[int] = int(sla_hours) if sla_hours is not None else None

        db_row = last_runs.get(routine_id)
        last_run: Optional[RoutineLastRun] = None
        if db_row:
            ran_at_raw = db_row.get("started_at")
            ran_at: Optional[datetime] = None
            if ran_at_raw is not None:
                if isinstance(ran_at_raw, datetime):
                    ran_at = ran_at_raw
                else:
                    try:
                        ran_at = datetime.fromisoformat(str(ran_at_raw))
                    except (ValueError, TypeError):
                        ran_at = None
            last_run = RoutineLastRun(
                run_id=db_row.get("run_id"),
                status=db_row.get("status"),
                rows_fetched=db_row.get("rows_fetched"),
                rows_inserted=db_row.get("rows_inserted"),
                rows_updated=db_row.get("rows_updated"),
                duration_ms=db_row.get("duration_ms"),
                error_message=db_row.get("error_message"),
                ran_at=ran_at,
            )

        ran_at_for_sla = last_run.ran_at if last_run else None
        sla_breached = _compute_sla_breached(sla_hours_int, ran_at_for_sla)
        display_status = _compute_display_status(manifest_status, False, sla_breached, last_run)
        _maybe_log_transition(routine_id, display_status)

        entries.append(
            RoutineEntry(
                id=routine_id,
                tables=tables,
                cadence=cadence,
                schedule=str(schedule) if schedule else None,
                source=str(source) if source else None,
                manifest_status=manifest_status,
                is_new=False,
                priority=None,
                sla_freshness_hours=sla_hours_int,
                last_run=last_run,
                sla_breached=sla_breached,
                display_status=display_status,
            )
        )

    # ---- new_routines (not yet built) ----
    for raw in new_raw:
        if not isinstance(raw, dict):
            continue
        routine_id = str(raw.get("id", ""))
        table_val = raw.get("target_table", "")
        tables = _parse_tables(table_val)
        cadence = str(raw.get("cadence", ""))
        schedule = raw.get("schedule")
        source_url = raw.get("source_url")
        priority = raw.get("priority")

        display_status = "planned"
        _maybe_log_transition(routine_id, display_status)

        entries.append(
            RoutineEntry(
                id=routine_id,
                tables=tables,
                cadence=cadence,
                schedule=str(schedule) if schedule else None,
                source=str(source_url) if source_url else None,
                manifest_status="planned",
                is_new=True,
                priority=str(priority) if priority else None,
                sla_freshness_hours=None,
                last_run=None,
                sla_breached=False,
                display_status=display_status,
            )
        )

    live_count = sum(1 for e in entries if e.display_status == "live")
    sla_breached_count = sum(1 for e in entries if e.sla_breached)

    return RoutinesResponse(
        routines=entries,
        total=len(entries),
        live_count=live_count,
        sla_breached_count=sla_breached_count,
        data_available=db_available,
        as_of=datetime.now(tz=IST),
    )


async def _check_db_available(session: AsyncSession) -> bool:
    """Return True if de_routine_runs is queryable at all (even if empty)."""
    try:
        await session.execute(text("SELECT 1 FROM de_routine_runs LIMIT 1"))
        return True
    except ProgrammingError:
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("de_routine_runs_check_failed", error=str(exc))
        return False
