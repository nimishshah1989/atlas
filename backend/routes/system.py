"""System endpoints — health, readiness, status, heartbeat, roadmap, quality, logs."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, Query, Response
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.core.roadmap_checks import evaluate_check
from backend.core.roadmap_loader import RoadmapFile, load_roadmap
from backend.db.session import async_session_factory, get_db
from backend.models.schemas import DataFreshness, StatusResponse
from backend.version import GIT_SHA, VERSION

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["system"])

IST = timezone(timedelta(hours=5, minutes=30))
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# TTL cache — simple in-process dict
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[Any, float]] = {}
_CACHE_TTL = 10.0  # seconds


def _cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry is None:
        return None
    val, ts = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return val


def _cache_set(key: str, val: Any) -> None:
    _cache[key] = (val, time.monotonic())


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class SystemHeartbeatResponse(BaseModel):
    memory_md_mtime: Optional[datetime]
    wiki_index_mtime: Optional[datetime]
    state_db_mtime: Optional[datetime]
    last_chunk_done_at: Optional[datetime]
    last_chunk_id: Optional[str]
    last_quality_run_at: Optional[datetime]
    last_quality_score: Optional[int]
    backend_uptime_seconds: int
    as_of: datetime
    last_smoke_run_at: Optional[datetime]
    last_smoke_result: Optional[str]
    last_smoke_summary: Optional[str]


class StepResponse(BaseModel):
    id: str
    text: str
    check: str  # ok | fail | slow-skipped | error
    detail: str


class ChunkResponse(BaseModel):
    id: str
    title: str
    status: str
    attempts: int
    updated_at: Optional[datetime]
    steps: list[StepResponse]


class RollupResponse(BaseModel):
    done: int
    total: int
    pct: int


class DemoGateResponse(BaseModel):
    url: str
    walkthrough: list[str]


class VersionResponse(BaseModel):
    id: str
    title: str
    goal: str
    status: str
    rollup: RollupResponse
    chunks: list[ChunkResponse]
    demo_gate: Optional[DemoGateResponse] = None


class SystemRoadmapResponse(BaseModel):
    as_of: datetime
    versions: list[VersionResponse]


class SystemQualityResponse(BaseModel):
    as_of: Optional[datetime]
    scores: Optional[Any]


class SystemLogsTailResponse(BaseModel):
    file: str
    lines: list[str]
    as_of: datetime


# ---------------------------------------------------------------------------
# Existing C11 endpoints (preserved exactly)
# ---------------------------------------------------------------------------


@router.get("/health")
async def health() -> dict:
    """Liveness probe — process is up and serving requests."""
    return {"status": "ok", "version": VERSION, "git_sha": GIT_SHA}


@router.get("/ready")
async def ready(response: Response) -> dict:
    """Readiness probe — dependencies (DB) reachable."""
    checks: dict[str, dict] = {}
    all_ok = True

    t0 = time.monotonic()
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {
            "status": "ok",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }
    except Exception as exc:
        all_ok = False
        checks["database"] = {"status": "fail", "error": str(exc)[:200]}

    if not all_ok:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if all_ok else "not_ready",
        "version": VERSION,
        "git_sha": GIT_SHA,
        "checks": checks,
    }


@router.get("/status", response_model=StatusResponse)
async def status(
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    """Get system status with data freshness info."""
    t0 = time.monotonic()
    svc = JIPDataService(db)
    freshness_data = await svc.get_data_freshness()

    elapsed = int((time.monotonic() - t0) * 1000)
    log.info("status_checked", ms=elapsed)

    return StatusResponse(
        freshness=DataFreshness(
            equity_ohlcv_as_of=freshness_data.get("technicals_as_of"),
            rs_scores_as_of=freshness_data.get("rs_scores_as_of"),
            technicals_as_of=freshness_data.get("technicals_as_of"),
            breadth_as_of=freshness_data.get("breadth_as_of"),
            regime_as_of=freshness_data.get("regime_as_of"),
            mf_holdings_as_of=freshness_data.get("mf_holdings_as_of"),
        ),
        active_stocks=freshness_data.get("active_stocks", 0),
        sectors=freshness_data.get("sectors", 0),
    )


# ---------------------------------------------------------------------------
# Helper: _file_mtime_ist
# ---------------------------------------------------------------------------


def _file_mtime_ist(path: Path) -> Optional[datetime]:
    """Return file mtime as IST-aware datetime, or None if missing."""
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=IST)
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Helper: _state_db_info
# ---------------------------------------------------------------------------

_STATE_DB = _REPO_ROOT / "orchestrator" / "state.db"


def _state_db_info() -> dict:
    """Read state.db for last DONE chunk. Returns dict with keys or None values."""
    result: dict = {
        "state_db_mtime": None,
        "last_chunk_done_at": None,
        "last_chunk_id": None,
        "last_quality_score": None,
        "last_quality_run_at": None,
    }
    if not _STATE_DB.exists():
        return result

    result["state_db_mtime"] = _file_mtime_ist(_STATE_DB)

    try:
        conn = sqlite3.connect(str(_STATE_DB))
        try:
            # Last DONE chunk
            row = conn.execute(
                "SELECT id, finished_at FROM chunks WHERE status='DONE' "
                "ORDER BY finished_at DESC LIMIT 1"
            ).fetchone()
            if row:
                chunk_id, finished_at_str = row
                result["last_chunk_id"] = chunk_id
                if finished_at_str:
                    try:
                        dt = datetime.fromisoformat(finished_at_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        result["last_chunk_done_at"] = dt.astimezone(IST)
                    except ValueError:
                        pass

            # Last quality run
            qrow = conn.execute(
                "SELECT overall_score, at FROM quality_runs ORDER BY at DESC LIMIT 1"
            ).fetchone()
            if qrow:
                score, at_str = qrow
                result["last_quality_score"] = int(score)
                if at_str:
                    try:
                        dt = datetime.fromisoformat(at_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        result["last_quality_run_at"] = dt.astimezone(IST)
                    except ValueError:
                        pass
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.warning("state_db_read_error", error=str(exc))

    return result


# ---------------------------------------------------------------------------
# Helper: _smoke_log_info
# ---------------------------------------------------------------------------

_SMOKE_SUMMARY_TRAILER_RE = __import__("re").compile(
    r"summary:\s*total=(\d+)\s+passed=(\d+)\s+hard_fail=(\d+)",
    __import__("re").IGNORECASE,
)


def _smoke_log_info() -> dict:
    """Read most recent *.smoke.log under orchestrator/logs/."""
    result: dict = {
        "last_smoke_run_at": None,
        "last_smoke_result": None,
        "last_smoke_summary": None,
    }
    logs_dir = _REPO_ROOT / "orchestrator" / "logs"
    smoke_logs = (
        sorted(
            logs_dir.glob("*.smoke.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if logs_dir.exists()
        else []
    )

    if not smoke_logs:
        return result

    latest = smoke_logs[0]
    result["last_smoke_run_at"] = _file_mtime_ist(latest)

    try:
        # Read last 20 lines for trailer
        text_lines = deque(latest.open(encoding="utf-8", errors="replace"), maxlen=20)
        for line in reversed(list(text_lines)):
            m = _SMOKE_SUMMARY_TRAILER_RE.search(line)
            if m:
                total = int(m.group(1))
                passed = int(m.group(2))
                hard_fail = int(m.group(3))
                result["last_smoke_summary"] = f"{passed}/{total} green"
                result["last_smoke_result"] = "green" if hard_fail == 0 else "red"
                break
    except OSError as exc:
        log.warning("smoke_log_read_error", error=str(exc))

    return result


# ---------------------------------------------------------------------------
# _PROCESS_START — backend start time for uptime
# ---------------------------------------------------------------------------

_PROCESS_START = time.monotonic()


# ---------------------------------------------------------------------------
# GET /api/v1/system/heartbeat
# ---------------------------------------------------------------------------


@router.get("/system/heartbeat", response_model=SystemHeartbeatResponse)
async def heartbeat() -> SystemHeartbeatResponse:
    """Heartbeat — 12-field status strip. 10s cached."""
    cached = _cache_get("heartbeat")
    if cached is not None:
        return cached

    memory_md = (
        Path.home()
        / ".claude"
        / "projects"
        / "-home-ubuntu-atlas"
        / "memory"
        / "MEMORY.md"
    )
    wiki_index = Path.home() / ".forge" / "knowledge" / "wiki" / "index.md"
    quality_report = _REPO_ROOT / ".quality" / "report.json"

    db_info = _state_db_info()
    smoke_info = _smoke_log_info()

    last_quality_run_at = db_info.get("last_quality_run_at")
    # Fall back to report.json mtime if not in DB
    if last_quality_run_at is None:
        last_quality_run_at = _file_mtime_ist(quality_report)

    resp = SystemHeartbeatResponse(
        memory_md_mtime=_file_mtime_ist(memory_md),
        wiki_index_mtime=_file_mtime_ist(wiki_index),
        state_db_mtime=db_info.get("state_db_mtime"),
        last_chunk_done_at=db_info.get("last_chunk_done_at"),
        last_chunk_id=db_info.get("last_chunk_id"),
        last_quality_run_at=last_quality_run_at,
        last_quality_score=db_info.get("last_quality_score"),
        backend_uptime_seconds=int(time.monotonic() - _PROCESS_START),
        as_of=datetime.now(IST),
        last_smoke_run_at=smoke_info.get("last_smoke_run_at"),
        last_smoke_result=smoke_info.get("last_smoke_result"),
        last_smoke_summary=smoke_info.get("last_smoke_summary"),
    )
    _cache_set("heartbeat", resp)
    return resp


# ---------------------------------------------------------------------------
# GET /api/v1/system/roadmap
# ---------------------------------------------------------------------------

_CHUNK_STATUS_MAP = {
    "DONE": "DONE",
    "IN_PROGRESS": "IN_PROGRESS",
    "PENDING": "PENDING",
    "PLANNED": "PLANNED",
    "BLOCKED": "BLOCKED",
    "FAILED": "FAILED",
}


def _load_chunk_states() -> dict[str, dict]:
    """Load chunk status/attempts/updated_at from state.db."""
    states: dict[str, dict] = {}
    if not _STATE_DB.exists():
        return states
    try:
        conn = sqlite3.connect(str(_STATE_DB))
        try:
            rows = conn.execute(
                "SELECT id, status, attempts, updated_at FROM chunks"
            ).fetchall()
            for row in rows:
                chunk_id, status, attempts, updated_at_str = row
                dt = None
                if updated_at_str:
                    try:
                        dt = datetime.fromisoformat(updated_at_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(IST)
                    except ValueError:
                        pass
                states[chunk_id] = {
                    "status": _CHUNK_STATUS_MAP.get(status, status),
                    "attempts": attempts or 0,
                    "updated_at": dt,
                }
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.warning("state_db_chunks_read_error", error=str(exc))
    return states


def _version_status(chunks: list[ChunkResponse]) -> str:
    if not chunks:
        return "EMPTY"
    statuses = {c.status for c in chunks}
    if statuses == {"DONE"}:
        return "DONE"
    if "IN_PROGRESS" in statuses:
        return "IN_PROGRESS"
    if "FAILED" in statuses:
        return "FAILED"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if any(s == "DONE" for c in chunks for s in [c.status]):
        return "IN_PROGRESS"
    return "PENDING"


def _version_rollup(chunks: list[ChunkResponse]) -> RollupResponse:
    total = len(chunks)
    done = sum(1 for c in chunks if c.status == "DONE")
    pct = int(done / total * 100) if total else 0
    return RollupResponse(done=done, total=total, pct=pct)


async def _build_roadmap_response(evaluate_slow: bool) -> SystemRoadmapResponse:
    roadmap: RoadmapFile = await asyncio.to_thread(load_roadmap)
    chunk_states = await asyncio.to_thread(_load_chunk_states)

    version_responses: list[VersionResponse] = []

    for version in roadmap.versions:
        chunk_responses: list[ChunkResponse] = []

        for chunk in version.chunks:
            state = chunk_states.get(chunk.id, {})
            status = state.get("status", "PENDING")
            attempts = state.get("attempts", 0)
            updated_at = state.get("updated_at")

            step_responses: list[StepResponse] = []
            for step in chunk.steps:
                check_result, detail = await asyncio.to_thread(
                    evaluate_check, step.check, evaluate_slow
                )
                step_responses.append(
                    StepResponse(
                        id=step.id,
                        text=step.text,
                        check=check_result,
                        detail=detail,
                    )
                )

            chunk_responses.append(
                ChunkResponse(
                    id=chunk.id,
                    title=chunk.title,
                    status=status,
                    attempts=attempts,
                    updated_at=updated_at,
                    steps=step_responses,
                )
            )

        v_status = _version_status(chunk_responses)
        rollup = _version_rollup(chunk_responses)

        demo_gate_resp = None
        if version.demo_gate:
            demo_gate_resp = DemoGateResponse(
                url=version.demo_gate.url,
                walkthrough=version.demo_gate.walkthrough,
            )

        version_responses.append(
            VersionResponse(
                id=version.id,
                title=version.title,
                goal=version.goal,
                status=v_status,
                rollup=rollup,
                chunks=chunk_responses,
                demo_gate=demo_gate_resp,
            )
        )

    return SystemRoadmapResponse(
        as_of=datetime.now(IST),
        versions=version_responses,
    )


@router.get("/system/roadmap", response_model=SystemRoadmapResponse)
async def roadmap(
    evaluate_slow: bool = Query(default=False),
) -> SystemRoadmapResponse:
    """Roadmap — parsed roadmap.yaml joined with state.db. 10s cached."""
    cache_key = f"roadmap:{evaluate_slow}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await asyncio.wait_for(
            _build_roadmap_response(evaluate_slow), timeout=15.0
        )
    except asyncio.TimeoutError:
        log.warning("roadmap_endpoint_timeout")
        # Return partial / empty with error
        resp = SystemRoadmapResponse(
            as_of=datetime.now(IST),
            versions=[],
        )

    _cache_set(cache_key, resp)
    return resp


# ---------------------------------------------------------------------------
# GET /api/v1/system/quality
# ---------------------------------------------------------------------------

_QUALITY_REPORT = _REPO_ROOT / ".quality" / "report.json"


@router.get("/system/quality", response_model=SystemQualityResponse)
async def quality() -> SystemQualityResponse:
    """Quality — returns .quality/report.json verbatim + as_of. 10s cached."""
    cached = _cache_get("quality")
    if cached is not None:
        return cached

    import json

    as_of = _file_mtime_ist(_QUALITY_REPORT)
    scores = None

    if _QUALITY_REPORT.exists():
        try:
            scores = json.loads(_QUALITY_REPORT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("quality_report_read_error", error=str(exc))

    resp = SystemQualityResponse(as_of=as_of, scores=scores)
    _cache_set("quality", resp)
    return resp


# ---------------------------------------------------------------------------
# GET /api/v1/system/logs/tail
# ---------------------------------------------------------------------------

_LOGS_DIR = _REPO_ROOT / "orchestrator" / "logs"
_MAX_LINES = 1000
_DEFAULT_LINES = 200


@router.get("/system/logs/tail", response_model=SystemLogsTailResponse)
async def logs_tail(
    lines: int = Query(default=_DEFAULT_LINES),
) -> SystemLogsTailResponse:
    """Log tail — last N lines from most recent orchestrator log. 10s cached."""
    # Clamp lines
    lines = max(0, min(lines, _MAX_LINES))

    cache_key = f"logs_tail:{lines}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    now = datetime.now(IST)

    if not _LOGS_DIR.exists():
        resp = SystemLogsTailResponse(file="", lines=[], as_of=now)
        _cache_set(cache_key, resp)
        return resp

    log_files = sorted(
        _LOGS_DIR.glob("*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not log_files:
        resp = SystemLogsTailResponse(file="", lines=[], as_of=now)
        _cache_set(cache_key, resp)
        return resp

    latest = log_files[0]
    tail_lines: list[str] = []

    if lines > 0:
        try:
            buf: deque[str] = deque(
                latest.open(encoding="utf-8", errors="replace"), maxlen=lines
            )
            tail_lines = [line.rstrip("\n") for line in buf]
        except OSError as exc:
            log.warning("log_tail_read_error", error=str(exc))

    # Return path relative to repo root
    try:
        rel_path = str(latest.relative_to(_REPO_ROOT))
    except ValueError:
        rel_path = str(latest)

    resp = SystemLogsTailResponse(file=rel_path, lines=tail_lines, as_of=now)
    _cache_set(cache_key, resp)
    return resp
