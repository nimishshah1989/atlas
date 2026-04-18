"""Macro routes — VIX, yield curve, FX rates, RBI policy rates.

GET /api/macros/vix           — India VIX time series (via JIPDerivativesService)
GET /api/macros/yield-curve   — G-Sec yield curve by tenor (via JIPMacroService)
GET /api/macros/fx            — RBI reference FX rates (via JIPMacroService)
GET /api/macros/policy-rates  — RBI policy rates: REPO/CRR/SLR/… (via JIPMacroService)

All routes return 503 with detail.reason when the underlying JIP table is
empty or stale (lag > 5 calendar days for daily data).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as _date
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query

from backend.clients.jip_derivatives_service import JIPDerivativesService
from backend.clients.jip_macro_service import JIPMacroService
from backend.db.session import async_session_factory
from backend.models.derivatives import VIXMeta, VIXPoint, VIXResponse
from backend.models.macros import (
    FXMeta,
    FXPoint,
    FXResponse,
    PolicyRateMeta,
    PolicyRatePoint,
    PolicyRateResponse,
    YieldCurveEntry,
    YieldCurveMeta,
    YieldCurveResponse,
    YieldPoint,
)

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


def _date_range_guard(from_date: _date, to_date: _date) -> None:
    """Raise HTTP 400 when from_date > to_date."""
    if from_date > to_date:
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


@router.get("/yield-curve", response_model=None)
async def get_yield_curve(
    from_date: Optional[_date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[_date] = Query(None, description="End date (inclusive)"),
) -> dict[str, Any]:
    """Return G-Sec yield curve time series via JIPMacroService.

    Each entry groups all tenor points for a single yield_date.
    Returns 503 when yield curve data is empty or stale (lag > 5 days).
    """
    today = _today()
    resolved_from = from_date or (today - timedelta(days=30))
    resolved_to = to_date or today
    _date_range_guard(resolved_from, resolved_to)

    async with async_session_factory() as session:
        svc = JIPMacroService(session)
        healthy, reason = await svc.check_yield_health()
        if not healthy:
            log.warning("macros_yield_health_fail", reason=reason)
            raise HTTPException(status_code=503, detail={"reason": reason})

        rows = await svc.get_yield_curve(resolved_from, resolved_to)

    # Group rows by yield_date → list[YieldCurveEntry]
    entries_by_date: dict[_date, list[YieldPoint]] = {}
    for r in rows:
        d: _date = r["yield_date"]
        pt = YieldPoint(
            tenor=r["tenor"],
            yield_pct=Decimal(str(r["yield_pct"])),
            security_name=r.get("security_name"),
            source=r.get("source"),
        )
        entries_by_date.setdefault(d, []).append(pt)

    entries = [
        YieldCurveEntry(yield_date=d, points=pts) for d, pts in sorted(entries_by_date.items())
    ]
    data_as_of = max(entries_by_date.keys(), default=None)

    return YieldCurveResponse(
        yield_curve=entries,
        meta=YieldCurveMeta(
            from_date=resolved_from,
            to_date=resolved_to,
            data_as_of=data_as_of,
            date_count=len(entries),
            point_count=sum(len(e.points) for e in entries),
        ),
    ).model_dump(mode="json")


@router.get("/fx", response_model=None)
async def get_fx_rates(
    from_date: Optional[_date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[_date] = Query(None, description="End date (inclusive)"),
    currency_pair: Optional[str] = Query(
        None, description="Filter by pair e.g. USD/INR (optional)"
    ),
) -> dict[str, Any]:
    """Return RBI reference FX rates via JIPMacroService.

    Supports USD/INR, EUR/INR, GBP/INR, JPY/INR.
    Returns 503 when FX rate data is empty or stale (lag > 5 days).
    """
    today = _today()
    resolved_from = from_date or (today - timedelta(days=30))
    resolved_to = to_date or today
    _date_range_guard(resolved_from, resolved_to)

    async with async_session_factory() as session:
        svc = JIPMacroService(session)
        healthy, reason = await svc.check_fx_health()
        if not healthy:
            log.warning("macros_fx_health_fail", reason=reason)
            raise HTTPException(status_code=503, detail={"reason": reason})

        rows = await svc.get_fx_rates(resolved_from, resolved_to, currency_pair)

    points = [
        FXPoint(
            rate_date=r["rate_date"],
            currency_pair=r["currency_pair"],
            reference_rate=Decimal(str(r["reference_rate"])),
            source=r.get("source"),
        )
        for r in rows
    ]
    data_as_of = max((p.rate_date for p in points), default=None)
    pairs_present = sorted({p.currency_pair for p in points})

    return FXResponse(
        fx_rates=points,
        meta=FXMeta(
            from_date=resolved_from,
            to_date=resolved_to,
            currency_pairs=pairs_present,
            data_as_of=data_as_of,
            point_count=len(points),
        ),
    ).model_dump(mode="json")


@router.get("/policy-rates", response_model=None)
async def get_policy_rates(
    from_date: Optional[_date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[_date] = Query(None, description="End date (inclusive)"),
    rate_type: Optional[str] = Query(
        None,
        description=("Filter by rate type: REPO, REVERSE_REPO, CRR, SLR, BANK_RATE (optional)"),
    ),
) -> dict[str, Any]:
    """Return RBI policy rates via JIPMacroService.

    Rate types: REPO, REVERSE_REPO, CRR, SLR, BANK_RATE.
    Returns 503 when policy rate data is empty or stale (lag > 5 days).
    """
    today = _today()
    resolved_from = from_date or (today - timedelta(days=90))
    resolved_to = to_date or today
    _date_range_guard(resolved_from, resolved_to)

    async with async_session_factory() as session:
        svc = JIPMacroService(session)
        healthy, reason = await svc.check_policy_health()
        if not healthy:
            log.warning("macros_policy_health_fail", reason=reason)
            raise HTTPException(status_code=503, detail={"reason": reason})

        rows = await svc.get_policy_rates(resolved_from, resolved_to, rate_type)

    points = [
        PolicyRatePoint(
            effective_date=r["effective_date"],
            rate_type=r["rate_type"],
            rate_pct=Decimal(str(r["rate_pct"])),
            source=r.get("source"),
        )
        for r in rows
    ]
    data_as_of = max((p.effective_date for p in points), default=None)
    types_present = sorted({p.rate_type for p in points})

    return PolicyRateResponse(
        policy_rates=points,
        meta=PolicyRateMeta(
            from_date=resolved_from,
            to_date=resolved_to,
            rate_types=types_present,
            data_as_of=data_as_of,
            point_count=len(points),
        ),
    ).model_dump(mode="json")
