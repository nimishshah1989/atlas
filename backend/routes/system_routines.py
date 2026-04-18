"""Routine visibility endpoint — GET /api/v1/system/routines.

Split from system.py to stay under the 500-line modularity gate.
Registered by a bare import at the bottom of backend/routes/system.py
(same pattern as system_roadmap).
"""

from __future__ import annotations

import time
from typing import Any, Optional, cast

import structlog
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.routines import RoutinesResponse
from backend.routes.system import router
from backend.services.routines_service import get_routines

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# 60s in-process cache (separate from system.py's 10s cache)
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[Any, float]] = {}
_CACHE_TTL = 60.0


def _cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry is None:
        return None
    cached_resp, ts = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return cached_resp


def _cache_set(key: str, cached_resp: Any) -> None:
    _cache[key] = (cached_resp, time.monotonic())


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


@router.get("/system/routines", response_model=RoutinesResponse)
async def routines(db: AsyncSession = Depends(get_db)) -> RoutinesResponse:
    """Routine visibility — one entry per JIP routine from jip-source-manifest.yaml.

    Enriched with last-run data from the JIP observability table (graceful
    degradation if the table is missing or empty). 60s cached.
    """
    cached = _cache_get("routines")
    if cached is not None:
        return cast(RoutinesResponse, cached)

    resp = await get_routines(db)
    _cache_set("routines", resp)
    return resp
