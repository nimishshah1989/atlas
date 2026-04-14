"""GET /api/v1/system/roadmap — split out of system.py to keep modules <500 lines."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import structlog
from fastapi import Query

from backend.core.roadmap_checks import evaluate_check
from backend.core.roadmap_loader import Chunk, RoadmapFile, load_roadmap

from .system import (
    IST,
    _STATE_DB,
    ChunkResponse,
    DemoGateResponse,
    MilestoneResponse,
    RollupResponse,
    StepResponse,
    SystemRoadmapResponse,
    VersionResponse,
    _cache_get,
    _cache_set,
    router,
)

# Filesystem signals consumed by the milestone strip. Wiki raw learnings
# live under ~/.forge/knowledge/raw/atlas/chunk-{id}-learnings.md (mixed
# case in the wild — case-insensitive match required). MEMORY.md is the
# orchestrator's auto-memory index; mtime ≥ chunk.finished_at means the
# memory sync ran after the chunk completed.
_WIKI_RAW_DIR = Path.home() / ".forge" / "knowledge" / "raw" / "atlas"
_MEMORY_MD = Path.home() / ".claude" / "projects" / "-home-ubuntu-atlas" / "memory" / "MEMORY.md"


def _milestone(name: str, status: str, detail: str | None = None) -> MilestoneResponse:
    return MilestoneResponse(name=name, status=status, detail=detail)


def _parse_iso_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _load_milestone_signals(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """One pass over transitions, quality_runs, sessions — return a per
    chunk_id dict the milestone computer can consume without further IO.

    The forge-runner state machine moves a chunk through PLANNING →
    IMPLEMENTING → TESTING → QUALITY_GATE → DONE; we read the
    `transitions` table (not `sessions.phase`, which uses different
    names like CLAUDE/POST_CHUNK) to know which states a chunk has
    actually entered."""
    signals: dict[str, dict[str, Any]] = {}

    try:
        for row in conn.execute("SELECT chunk_id, to_state FROM transitions"):
            cid, to_state = row
            chunk_signals = signals.setdefault(cid, {})
            states_seen = chunk_signals.setdefault("states_seen", set())
            states_seen.add(to_state)
    except sqlite3.OperationalError:
        pass  # transitions table may not exist yet

    try:
        for row in conn.execute(
            "SELECT chunk_id, passed, overall_score, at FROM quality_runs ORDER BY id ASC"
        ):
            cid, passed, overall_score, at = row
            chunk_signals = signals.setdefault(cid, {})
            chunk_signals["latest_quality"] = {
                "passed": bool(passed),
                "overall_score": overall_score,
                "at": at,
            }
    except sqlite3.OperationalError:
        pass  # quality_runs table may not exist yet

    # Post-chunk session exit code — surfaces post-chunk.sh failures
    # (forge-compile, memory sync, smoke probe). Last row wins per chunk.
    try:
        for row in conn.execute(
            "SELECT chunk_id, exit_code FROM sessions WHERE phase='POST_CHUNK' ORDER BY id ASC"
        ):
            cid, exit_code = row
            signals.setdefault(cid, {})["post_chunk_exit"] = exit_code
    except sqlite3.OperationalError:
        pass  # sessions table may not exist yet

    return signals


def _load_wiki_chunk_index() -> set[str]:
    """Return the set of lowercase chunk ids that have a wiki raw
    learnings file. Single directory listing, cached for the request."""
    if not _WIKI_RAW_DIR.exists():
        return set()
    out: set[str] = set()
    prefix = "chunk-"
    suffix = "-learnings.md"
    for entry in _WIKI_RAW_DIR.iterdir():
        name = entry.name
        if name.startswith(prefix) and name.endswith(suffix):
            out.add(name[len(prefix) : -len(suffix)].lower())
    return out


def _memory_md_mtime() -> datetime | None:
    if not _MEMORY_MD.exists():
        return None
    return datetime.fromtimestamp(_MEMORY_MD.stat().st_mtime, tz=timezone.utc)


def _compute_milestones(
    chunk_id: str,
    chunk_status: str,
    finished_at: datetime | None,
    signals: dict[str, Any],
    wiki_index: set[str],
    memory_mtime: datetime | None,
) -> list[MilestoneResponse]:
    """Derive the 7-dot process strip for one chunk. Order is fixed and
    matches the frontend strip — do not reorder without updating the
    chunk card. Each milestone is one of: green | amber | red | pending."""

    out: list[MilestoneResponse] = []
    states_seen: set[str] = signals.get("states_seen", set())
    latest_quality = signals.get("latest_quality")
    post_chunk_exit = signals.get("post_chunk_exit")
    is_done = chunk_status == "DONE"
    is_failed = chunk_status == "FAILED"

    # 1. planned — chunk entered PLANNING at least once.
    if "PLANNING" in states_seen:
        out.append(_milestone("planned", "green", "transitioned to PLANNING"))
    else:
        out.append(_milestone("planned", "pending", "no PLANNING transition yet"))

    # 2. implemented — chunk reached IMPLEMENTING (claude session ran).
    if "IMPLEMENTING" in states_seen:
        out.append(_milestone("implemented", "green", "transitioned to IMPLEMENTING"))
    elif is_failed:
        out.append(_milestone("implemented", "red", "failed before IMPLEMENTING"))
    else:
        out.append(_milestone("implemented", "pending", "not yet IMPLEMENTING"))

    # 3. tests — chunk reached TESTING (verifier ran).
    if "TESTING" in states_seen:
        out.append(_milestone("tests", "green", "transitioned to TESTING"))
    elif is_failed:
        out.append(_milestone("tests", "red", "failed before TESTING"))
    else:
        out.append(_milestone("tests", "pending", "not yet TESTING"))

    # 4. quality_gate — quality_runs.passed for the latest run.
    if latest_quality is None:
        out.append(_milestone("quality_gate", "pending", "no quality_runs row"))
    elif latest_quality["passed"]:
        score = latest_quality.get("overall_score")
        out.append(_milestone("quality_gate", "green", f"7-dim gate passed (score={score})"))
    else:
        score = latest_quality.get("overall_score")
        out.append(_milestone("quality_gate", "red", f"7-dim gate failed (score={score})"))

    # 5. post_chunk — POST_CHUNK session exit code from sessions table.
    # exit 0 = post-chunk.sh ran clean (commit+push+restart+smoke).
    # exit !=0 = sync gap (most often forge-compile or memory step failed).
    if post_chunk_exit is None:
        if is_done:
            out.append(_milestone("post_chunk", "amber", "DONE but no POST_CHUNK session row"))
        else:
            out.append(_milestone("post_chunk", "pending", "post_chunk not yet run"))
    elif post_chunk_exit == 0:
        out.append(_milestone("post_chunk", "green", "post_chunk.sh exit 0"))
    else:
        out.append(_milestone("post_chunk", "red", f"post_chunk.sh exit {post_chunk_exit}"))

    # 6. wiki — raw learnings file exists for this chunk.
    in_wiki = chunk_id.lower() in wiki_index
    if in_wiki:
        out.append(_milestone("wiki", "green", "raw learnings file present"))
    elif is_done:
        out.append(_milestone("wiki", "amber", "DONE but no learnings file yet"))
    else:
        out.append(_milestone("wiki", "pending", "no learnings file"))

    # 7. memory — MEMORY.md mtime ≥ chunk.finished_at.
    if memory_mtime is None:
        out.append(_milestone("memory", "pending", "MEMORY.md missing"))
    elif finished_at is not None and memory_mtime >= finished_at:
        out.append(_milestone("memory", "green", "MEMORY.md updated after chunk finished"))
    elif is_done:
        out.append(_milestone("memory", "amber", "DONE but MEMORY.md older than finish time"))
    else:
        out.append(_milestone("memory", "pending", "chunk not finished"))

    return out


log = structlog.get_logger()

_SHIP_STATE_FILE = Path(__file__).resolve().parents[2] / ".forge" / "last-run.json"


def _load_ship_state() -> dict[str, Any]:
    """Read .forge/last-run.json if present. Single-slot state written by
    scripts/forge-ship.sh — tells the dashboard which chunk last went
    through the enforced tests+gate+memory chain and when."""
    if not _SHIP_STATE_FILE.exists():
        return {}
    try:
        ship_state_raw = json.loads(_SHIP_STATE_FILE.read_text())
        if not isinstance(ship_state_raw, dict):
            return {}
        return ship_state_raw
    except (OSError, ValueError):
        return {}


_CHUNK_STATUS_MAP = {
    "DONE": "DONE",
    "IN_PROGRESS": "IN_PROGRESS",
    "PENDING": "PENDING",
    "PLANNED": "PLANNED",
    "BLOCKED": "BLOCKED",
    "FAILED": "FAILED",
}


def _load_chunk_states() -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    if not _STATE_DB.exists():
        return states
    wiki_index = _load_wiki_chunk_index()
    memory_mtime = _memory_md_mtime()
    try:
        conn = sqlite3.connect(f"file:{_STATE_DB}?mode=ro&immutable=1", uri=True)
        try:
            signals = _load_milestone_signals(conn)
            rows = conn.execute(
                "SELECT id, title, status, attempts, last_error, updated_at,"
                " finished_at FROM chunks"
            ).fetchall()
            for row in rows:
                (
                    chunk_id,
                    title,
                    status,
                    attempts,
                    last_error,
                    updated_at_str,
                    finished_at_str,
                ) = row
                updated_dt = _parse_iso_utc(updated_at_str)
                finished_dt = _parse_iso_utc(finished_at_str)
                mapped_status = _CHUNK_STATUS_MAP.get(status, status)
                milestones = _compute_milestones(
                    chunk_id=chunk_id,
                    chunk_status=mapped_status,
                    finished_at=finished_dt,
                    signals=signals.get(chunk_id, {}),
                    wiki_index=wiki_index,
                    memory_mtime=memory_mtime,
                )
                states[chunk_id] = {
                    "title": title or "",
                    "status": mapped_status,
                    "attempts": attempts or 0,
                    "last_error": last_error,
                    "updated_at": (updated_dt.astimezone(IST) if updated_dt else None),
                    "milestones": milestones,
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
    chunk: Chunk,
    chunk_states: dict[str, dict[str, Any]],
    evaluate_slow: bool,
    ship_state: dict[str, Any],
) -> ChunkResponse:
    state = chunk_states.get(chunk.id, {})
    step_responses: list[StepResponse] = []
    for step in chunk.steps:
        check_result, detail = await asyncio.to_thread(evaluate_check, step.check, evaluate_slow)
        step_responses.append(
            StepResponse(id=step.id, text=step.text, check=check_result, detail=detail)
        )
    last_shipped_at = None
    last_ship_ok = None
    if ship_state.get("chunk") == chunk.id and "ts" in ship_state:
        try:
            last_shipped_at = datetime.fromtimestamp(
                int(ship_state["ts"]), tz=timezone.utc
            ).astimezone(IST)
            last_ship_ok = all(
                bool(ship_state.get(k, False)) for k in ("tests_ok", "quality_ok", "memory_ok")
            )
        except (TypeError, ValueError):
            pass
    return ChunkResponse(
        id=chunk.id,
        title=chunk.title,
        status=state.get("status", "PENDING"),
        attempts=state.get("attempts", 0),
        updated_at=state.get("updated_at"),
        steps=step_responses,
        last_error=state.get("last_error"),
        last_shipped_at=last_shipped_at,
        last_ship_ok=last_ship_ok,
        milestones=state.get("milestones", []),
    )


def _build_orphan_lane(
    chunk_states: dict[str, dict[str, Any]],
    referenced_ids: set[str],
    ship_state: dict[str, Any],
) -> VersionResponse | None:
    """Fold orphan chunks (in state.db but missing from roadmap.yaml) into a
    synthetic 'Quality & Infra' lane so every running chunk is visible on
    the dashboard. Without this the orchestrator can be executing a chunk
    the UI has no node for — which is exactly how S1–S4 went invisible."""
    orphan_ids = sorted(cid for cid in chunk_states if cid not in referenced_ids)
    if not orphan_ids:
        return None

    def _ship_fields(cid: str) -> tuple[datetime | None, bool | None]:
        if ship_state.get("chunk") != cid or "ts" not in ship_state:
            return None, None
        try:
            dt = datetime.fromtimestamp(int(ship_state["ts"]), tz=timezone.utc).astimezone(IST)
            ok = all(
                bool(ship_state.get(k, False)) for k in ("tests_ok", "quality_ok", "memory_ok")
            )
            return dt, ok
        except (TypeError, ValueError):
            return None, None

    orphan_chunks = []
    for cid in orphan_ids:
        dt, ok = _ship_fields(cid)
        orphan_chunks.append(
            ChunkResponse(
                id=cid,
                title=chunk_states[cid].get("title") or "",
                status=chunk_states[cid].get("status", "PENDING"),
                attempts=chunk_states[cid].get("attempts", 0),
                updated_at=chunk_states[cid].get("updated_at"),
                steps=[],
                last_error=chunk_states[cid].get("last_error"),
                last_shipped_at=dt,
                last_ship_ok=ok,
                milestones=chunk_states[cid].get("milestones", []),
            )
        )
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
    ship_state = await asyncio.to_thread(_load_ship_state)

    version_responses: list[VersionResponse] = []
    referenced_ids: set[str] = set()

    for version in roadmap_file.versions:
        chunk_responses = [
            await _build_chunk_response(c, chunk_states, evaluate_slow, ship_state)
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

    orphan_lane = _build_orphan_lane(chunk_states, referenced_ids, ship_state)
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
        return cast(SystemRoadmapResponse, cached)

    try:
        resp = await asyncio.wait_for(_build_roadmap_response(evaluate_slow), timeout=15.0)
    except asyncio.TimeoutError:
        log.warning("roadmap_endpoint_timeout")
        resp = SystemRoadmapResponse(
            as_of=datetime.now(IST),
            versions=[],
        )

    _cache_set(cache_key, resp)
    return resp
