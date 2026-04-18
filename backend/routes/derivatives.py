"""Derivatives routes — PCR + OI buildup (gated on JIP data health).

GET /api/derivatives/pcr/{symbol}  — Put/Call Ratio time series
GET /api/derivatives/{symbol}/oi   — OI buildup chart

Both routes do an inline freshness/row-count check via JIPDerivativesService.
Returns 503 {"reason": "..."} when the table is empty or stale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as _date
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query

from backend.clients.jip_derivatives_service import JIPDerivativesService
from backend.db.session import async_session_factory
from backend.models.derivatives import (
    OIMeta,
    OIPoint,
    OIResponse,
    PCRMeta,
    PCRPoint,
    PCRResponse,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/derivatives", tags=["derivatives"])


def _today() -> _date:
    return datetime.now(UTC).date()


# IMPORTANT: /pcr/{symbol} must be registered BEFORE /{symbol}/oi
# to prevent FastAPI capturing "pcr" as a symbol param.


@router.get("/pcr/{symbol}", response_model=None)
async def get_pcr(
    symbol: str,
    from_date: Optional[_date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[_date] = Query(None, description="End date (inclusive)"),
) -> dict[str, Any]:
    """Return Put/Call Ratio time series for a symbol.

    Source: JIP F&O data via JIPDerivativesService (pre-computed or computed).
    Returns 503 when F&O data is unavailable/stale.
    """
    today = _today()
    resolved_from = from_date or (today - timedelta(days=30))
    resolved_to = to_date or today

    if resolved_from > resolved_to:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_DATE_RANGE",
                    "message": "from_date must be <= to_date",
                    "details": {},
                }
            },
        )

    async with async_session_factory() as session:
        svc = JIPDerivativesService(session)
        healthy, reason = await svc.check_fo_health()
        if not healthy:
            log.warning("derivatives_pcr_health_fail", symbol=symbol, reason=reason)
            raise HTTPException(status_code=503, detail={"reason": reason})

        rows, source = await svc.get_pcr_series(symbol.upper(), resolved_from, resolved_to)

    points = [
        PCRPoint(
            trade_date=r["trade_date"],
            pcr_oi=Decimal(str(r["pcr_oi"])) if r.get("pcr_oi") is not None else None,
            pcr_volume=(Decimal(str(r["pcr_volume"])) if r.get("pcr_volume") is not None else None),
            total_oi=int(r["total_oi"]) if r.get("total_oi") is not None else None,
        )
        for r in rows
    ]
    data_as_of = max((p.trade_date for p in points), default=None)

    return PCRResponse(
        data=points,
        meta=PCRMeta(
            symbol=symbol.upper(),
            from_date=resolved_from,
            to_date=resolved_to,
            data_as_of=data_as_of,
            data_source=source,
            point_count=len(points),
        ),
    ).model_dump(mode="json")


@router.get("/{symbol}/oi", response_model=None)
async def get_oi_buildup(
    symbol: str,
    from_date: Optional[_date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[_date] = Query(None, description="End date (inclusive)"),
) -> dict[str, Any]:
    """Return OI buildup chart for a symbol.

    Daily total open interest + change-in-OI, split by option type (CE/PE/FUT).
    Returns 503 when F&O data is unavailable/stale.
    """
    today = _today()
    resolved_from = from_date or (today - timedelta(days=30))
    resolved_to = to_date or today

    if resolved_from > resolved_to:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_DATE_RANGE",
                    "message": "from_date must be <= to_date",
                    "details": {},
                }
            },
        )

    async with async_session_factory() as session:
        svc = JIPDerivativesService(session)
        healthy, reason = await svc.check_fo_health()
        if not healthy:
            log.warning("derivatives_oi_health_fail", symbol=symbol, reason=reason)
            raise HTTPException(status_code=503, detail={"reason": reason})

        rows = await svc.get_oi_buildup(symbol.upper(), resolved_from, resolved_to)

    points = [
        OIPoint(
            trade_date=r["trade_date"],
            option_type=r.get("option_type"),
            total_oi=int(r["total_oi"]),
            change_in_oi=int(r["change_in_oi"]),
        )
        for r in rows
    ]
    data_as_of = max((p.trade_date for p in points), default=None)

    return OIResponse(
        data=points,
        meta=OIMeta(
            symbol=symbol.upper(),
            from_date=resolved_from,
            to_date=resolved_to,
            data_as_of=data_as_of,
            point_count=len(points),
        ),
    ).model_dump(mode="json")
