"""GET /api/v1/system/roadmap — split out of system.py to keep modules <500 lines."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

import structlog
from fastapi import Query

from backend.core.roadmap_checks import evaluate_check
from backend.core.roadmap_loader import RoadmapFile, load_roadmap

from .system import (
    IST,
    _STATE_DB,
    ChunkResponse,
    DemoGateResponse,
    RollupResponse,
    StepResponse,
    SystemRoadmapResponse,
    VersionResponse,
    _cache_get,
    _cache_set,
    router,
)

log = structlog.get_logger()

_CHUNK_STATUS_MAP = {
    "DONE": "DONE",
    "IN_PROGRESS": "IN_PROGRESS",
    "PENDING": "PENDING",
    "PLANNED": "PLANNED",
    "BLOCKED": "BLOCKED",
    "FAILED": "FAILED",
}


def _load_chunk_states() -> dict[str, dict]:
    states: dict[str, dict] = {}
    if not _STATE_DB.exists():
        return states
    try:
        conn = sqlite3.connect(f"file:{_STATE_DB}?mode=ro&immutable=1", uri=True)
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
    roadmap_file: RoadmapFile = await asyncio.to_thread(load_roadmap)
    chunk_states = await asyncio.to_thread(_load_chunk_states)

    version_responses: list[VersionResponse] = []

    for version in roadmap_file.versions:
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
        resp = SystemRoadmapResponse(
            as_of=datetime.now(IST),
            versions=[],
        )

    _cache_set(cache_key, resp)
    return resp
