"""Health + readiness probes for atlas-backend.

Split out of `system.py` because that module hosts the big dashboard
endpoints (heartbeat / quality / logs) and was creeping past the 500-line
modularity budget. Keeping probes in their own module also makes it
obvious to load-balancer owners which file governs /health and /ready.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi import status as http_status
from sqlalchemy import text

from backend.db.session import async_session_factory
from backend.version import GIT_SHA, VERSION

probes_router = APIRouter(prefix="/api/v1", tags=["system"])


@probes_router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — process is up and serving requests."""
    return {"status": "ok", "version": VERSION, "git_sha": GIT_SHA}


@probes_router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, Any]:
    """Readiness probe — DB reachable AND cache prewarm complete.

    Returns 503 until `_prewarm_caches()` has populated the equity/MF
    aggregate caches. Callers (quality gate, systemd, k8s) should block
    on this endpoint so the first live-API probe doesn't race a cold JIP
    query that would blow past its latency budget.
    """
    checks: dict[str, dict[str, Any]] = {}
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

    prewarm_event = getattr(request.app.state, "prewarm_done", None)
    if prewarm_event is None:
        checks["prewarm"] = {"status": "unknown"}
    elif prewarm_event.is_set():
        checks["prewarm"] = {"status": "ok"}
    else:
        all_ok = False
        checks["prewarm"] = {"status": "pending"}

    if not all_ok:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if all_ok else "not_ready",
        "version": VERSION,
        "git_sha": GIT_SHA,
        "checks": checks,
    }
