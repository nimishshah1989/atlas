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
                "SELECT id, title, status, attempts, last_error, updated_at FROM chunks"
            ).fetchall()
            for row in rows:
                chunk_id, title, status, attempts, last_error, updated_at_str = row
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
                    "title": title or "",
                    "status": _CHUNK_STATUS_MAP.get(status, status),
                    "attempts": attempts or 0,
                    "last_error": last_error,
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


async def _build_chunk_response(
    chunk, chunk_states: dict[str, dict], evaluate_slow: bool
) -> ChunkResponse:
    state = chunk_states.get(chunk.id, {})
    step_responses: list[StepResponse] = []
    for step in chunk.steps:
        check_result, detail = await asyncio.to_thread(
            evaluate_check, step.check, evaluate_slow
        )
        step_responses.append(
            StepResponse(id=step.id, text=step.text, check=check_result, detail=detail)
        )
    return ChunkResponse(
        id=chunk.id,
        title=chunk.title,
        status=state.get("status", "PENDING"),
        attempts=state.get("attempts", 0),
        updated_at=state.get("updated_at"),
        steps=step_responses,
        last_error=state.get("last_error"),
    )


def _build_orphan_lane(
    chunk_states: dict[str, dict], referenced_ids: set[str]
) -> VersionResponse | None:
    """Fold orphan chunks (in state.db but missing from roadmap.yaml) into a
    synthetic 'Quality & Infra' lane so every running chunk is visible on
    the dashboard. Without this the orchestrator can be executing a chunk
    the UI has no node for — which is exactly how S1–S4 went invisible."""
    orphan_ids = sorted(cid for cid in chunk_states if cid not in referenced_ids)
    if not orphan_ids:
        return None
    orphan_chunks = [
        ChunkResponse(
            id=cid,
            title=chunk_states[cid].get("title") or "",
            status=chunk_states[cid].get("status", "PENDING"),
            attempts=chunk_states[cid].get("attempts", 0),
            updated_at=chunk_states[cid].get("updated_at"),
            steps=[],
            last_error=chunk_states[cid].get("last_error"),
        )
        for cid in orphan_ids
    ]
    return VersionResponse(
        id="SX",
        title="Quality & Infra (orphan chunks from state.db)",
        goal=(
            "Chunks tracked by the orchestrator but not declared in "
            "roadmap.yaml. Surfaced so no running chunk is invisible."
        ),
        status=_version_status(orphan_chunks),
        rollup=_version_rollup(orphan_chunks),
        chunks=orphan_chunks,
        demo_gate=None,
    )


async def _build_roadmap_response(evaluate_slow: bool) -> SystemRoadmapResponse:
    roadmap_file: RoadmapFile = await asyncio.to_thread(load_roadmap)
    chunk_states = await asyncio.to_thread(_load_chunk_states)

    version_responses: list[VersionResponse] = []
    referenced_ids: set[str] = set()

    for version in roadmap_file.versions:
        chunk_responses = [
            await _build_chunk_response(c, chunk_states, evaluate_slow)
            for c in version.chunks
        ]
        referenced_ids.update(c.id for c in version.chunks)

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
                status=_version_status(chunk_responses),
                rollup=_version_rollup(chunk_responses),
                chunks=chunk_responses,
                demo_gate=demo_gate_resp,
            )
        )

    orphan_lane = _build_orphan_lane(chunk_states, referenced_ids)
    if orphan_lane is not None:
        version_responses.append(orphan_lane)

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
