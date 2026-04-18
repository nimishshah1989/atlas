"""health_gate — FastAPI dependency that raises 503 if a data domain is failing.

Usage:
    from backend.core.health_gate import health_gate
    from fastapi import Depends

    @router.get("/my/route")
    async def my_route(gate: None = Depends(health_gate("equity_ohlcv"))):
        ...

Fail-open: if data-health.json does not exist yet, all domains pass through.
The file is read with a 60s in-process cache to avoid repeated disk reads.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import structlog
from fastapi import HTTPException

log = structlog.get_logger()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_HEALTH_PATH = _REPO_ROOT / "data-health.json"
_CACHE_TTL = 60.0

_health_cache: dict[str, tuple[Any, float]] = {}


def _load_health() -> list[dict[str, Any]]:
    """Load data-health.json with 60s in-process cache."""
    cached = _health_cache.get("tables")
    if cached is not None:
        cached_tables, ts = cached
        if time.monotonic() - ts < _CACHE_TTL:
            return cached_tables  # type: ignore[no-any-return]
    if not _DATA_HEALTH_PATH.exists():
        _health_cache["tables"] = ([], time.monotonic())
        return []
    try:
        payload = json.loads(_DATA_HEALTH_PATH.read_text(encoding="utf-8"))
        tables: list[dict[str, Any]] = payload.get("tables", [])
    except Exception as exc:
        log.warning("health_gate_load_error", error=str(exc))
        tables = []
    _health_cache["tables"] = (tables, time.monotonic())
    return tables


def health_gate(domain: str) -> Callable[[], None]:
    """FastAPI dependency factory. Raises HTTP 503 if any table in `domain` is failing.

    Fails open when data-health.json is missing (file not yet generated).
    Domain tables not found in the file also pass through.

    Args:
        domain: Domain name as declared in data-coverage.yaml (e.g. "equity_ohlcv").

    Returns:
        A callable suitable for use with FastAPI's Depends().
    """

    def _check() -> None:
        tables = _load_health()
        domain_tables = [t for t in tables if t.get("domain") == domain]
        if not domain_tables:
            # No health data for this domain — fail open.
            return
        failing = [t for t in domain_tables if not t.get("pass", True)]
        if failing:
            detail = {
                "error": "data_domain_unhealthy",
                "domain": domain,
                "failing_tables": [
                    {
                        "table": t["table"],
                        "overall_score": t.get("overall_score"),
                        "error": t.get("error"),
                        "dimensions": [
                            d for d in t.get("dimensions", []) if d.get("score", 100) < 80
                        ],
                    }
                    for t in failing
                ],
            }
            raise HTTPException(status_code=503, detail=detail)

    return _check
