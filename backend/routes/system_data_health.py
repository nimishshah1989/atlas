"""GET /api/v1/system/data-health — serve data-health.json content.

Split from system.py to stay under the 500-line modularity gate.
Registered by a bare import at the bottom of backend/routes/system.py
(same pattern as system_roadmap and system_routines).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional, cast

import structlog
from pydantic import BaseModel

from backend.routes.system import router

log = structlog.get_logger()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_HEALTH_PATH = _REPO_ROOT / "data-health.json"
_CACHE_TTL = 60.0

_cache: dict[str, tuple[Any, float]] = {}


class DataHealthResponse(BaseModel):
    generated_at: Optional[str] = None
    manifest_version: Optional[int] = None
    rubric: Optional[Any] = None
    tables: list[Any] = []
    available: bool  # False if data-health.json not yet generated


@router.get("/system/data-health", response_model=DataHealthResponse)
async def data_health() -> DataHealthResponse:
    """Data health — returns data-health.json produced by check-data-coverage.py. 60s cached."""
    cached = _cache.get("data_health")
    if cached is not None:
        cached_resp, ts = cached
        if time.monotonic() - ts < _CACHE_TTL:
            return cast(DataHealthResponse, cached_resp)

    if not _DATA_HEALTH_PATH.exists():
        resp = DataHealthResponse(
            generated_at=None,
            manifest_version=None,
            rubric=None,
            tables=[],
            available=False,
        )
        _cache["data_health"] = (resp, time.monotonic())
        return resp

    try:
        payload = json.loads(_DATA_HEALTH_PATH.read_text(encoding="utf-8"))
        resp = DataHealthResponse(
            generated_at=payload.get("generated_at"),
            manifest_version=payload.get("manifest_version"),
            rubric=payload.get("rubric"),
            tables=payload.get("tables", []),
            available=True,
        )
    except Exception as exc:
        log.warning("data_health_read_error", error=str(exc))
        resp = DataHealthResponse(
            generated_at=None,
            manifest_version=None,
            rubric=None,
            tables=[],
            available=False,
        )

    _cache["data_health"] = (resp, time.monotonic())
    return resp
