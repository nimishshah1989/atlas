"""Screener route — GET /api/v1/screener.

Exposes the 4-factor conviction engine as a paginated endpoint.
ScreenerResponse is defined here (not in conviction.py) to avoid a circular
import: conviction.py must not import from schemas.py, which imports from it.
"""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_market_service import JIPMarketService
from backend.db.session import get_db
from backend.models.conviction import (
    ActionSignal,
    ConvictionLevel,
    ScreenerRow,
)
from backend.models.schemas import ResponseMeta
from backend.services.conviction_engine import compute_screener_bulk

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])

_VALID_UNIVERSE = {"nifty50", "nifty200", "nifty500"}
_VALID_CONVICTION = {e.value for e in ConvictionLevel}
_VALID_ACTION = {e.value for e in ActionSignal}


class ScreenerResponse(BaseModel):
    """Screener paginated response."""

    rows: list[ScreenerRow]
    meta: ResponseMeta


@router.get("", response_model=ScreenerResponse)
async def get_screener(
    universe: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    conviction: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ScreenerResponse:
    """Return paginated equity rows with conviction/action/urgency signals.

    Filters (all optional):
    - universe: nifty50 | nifty200 | nifty500
    - sector: exact sector string
    - conviction: HIGH+ | HIGH | MEDIUM | LOW | AVOID
    - action: BUY | ACCUMULATE | WATCH | REDUCE | EXIT

    Pagination:
    - limit: 1-200 (default 50)
    - offset: 0+ (default 0)
    """
    if universe is not None and universe not in _VALID_UNIVERSE:
        raise HTTPException(
            status_code=422,
            detail=f"universe must be one of {sorted(_VALID_UNIVERSE)}",
        )
    if conviction is not None and conviction not in _VALID_CONVICTION:
        raise HTTPException(
            status_code=422,
            detail=f"conviction must be one of {sorted(_VALID_CONVICTION)}",
        )
    if action is not None and action not in _VALID_ACTION:
        raise HTTPException(
            status_code=422,
            detail=f"action must be one of {sorted(_VALID_ACTION)}",
        )

    t0 = time.perf_counter()

    regime_str = "SIDEWAYS"
    try:
        regime_svc = JIPMarketService(db)
        regime_data = await regime_svc.get_market_regime()
        regime_str = (regime_data.get("regime") if regime_data else None) or "SIDEWAYS"
    except (KeyError, TypeError, OSError):
        pass  # best-effort: regime fetch failure must not crash screener

    filters = {
        "universe": universe,
        "sector": sector,
        "conviction": conviction,
        "action": action,
        "limit": limit,
        "offset": offset,
        "regime": regime_str,
    }
    rows = await compute_screener_bulk(filters, db)
    screener_rows = [ScreenerRow(**row) for row in rows]
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return ScreenerResponse(
        rows=screener_rows,
        meta=ResponseMeta(
            record_count=len(screener_rows),
            offset=offset,
            limit=limit,
            query_ms=elapsed_ms,
        ),
    )
