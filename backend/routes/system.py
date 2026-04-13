"""System endpoints — health, readiness, status."""

import time

import structlog
from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.db.session import async_session_factory, get_db
from backend.models.schemas import DataFreshness, StatusResponse
from backend.version import GIT_SHA, VERSION

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["system"])


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
