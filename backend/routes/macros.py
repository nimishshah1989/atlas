"""Macro routes — VIX + (future: yield curve, FX, policy events).

GET /api/macros/vix — India VIX time series (via JIPDerivativesService, ticker='INDIAVIX')

Returns 503 when VIX data is unavailable/stale.
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
from backend.models.derivatives import VIXMeta, VIXPoint, VIXResponse

log = structlog.get_logger()
router = APIRouter(prefix="/api/macros", tags=["macros"])


def _today() -> _date:
    return datetime.now(UTC).date()


@router.get("/vix", response_model=None)
async def get_vix(
    from_date: Optional[_date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[_date] = Query(None, description="End date (inclusive)"),
) -> dict[str, Any]:
    """Return India VIX time series.

    Source: JIPDerivativesService macro values, ticker='INDIAVIX'.
    Returns 503 when VIX data is unavailable or stale (lag > 5 calendar days).
    """
    today = _today()
    resolved_from = from_date or (today - timedelta(days=90))
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
        healthy, reason = await svc.check_vix_health()
        if not healthy:
            log.warning("macros_vix_health_fail", reason=reason)
            raise HTTPException(status_code=503, detail={"reason": reason})

        rows = await svc.get_india_vix(resolved_from, resolved_to)

    points = [
        VIXPoint(
            trade_date=r["trade_date"],
            close=Decimal(str(r["close"])),
        )
        for r in rows
    ]
    data_as_of = max((p.trade_date for p in points), default=None)

    return VIXResponse(
        vix_series=points,
        meta=VIXMeta(
            ticker="INDIAVIX",
            from_date=resolved_from,
            to_date=resolved_to,
            data_as_of=data_as_of,
            point_count=len(points),
        ),
    ).model_dump(mode="json")
