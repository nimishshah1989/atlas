"""System endpoints — health and status."""

import time

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.db.session import get_db
from backend.models.schemas import DataFreshness, StatusResponse

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


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
