"""Instruments API routes — price series with optional back-adjustment.

GET /api/instruments/{symbol}/price
  ?adjusted=true (default) — back-adjusted prices continuous across corporate actions
  ?adjusted=false — raw prices with artificial jumps preserved
  ?from_date — ISO date, default today-365d
  ?to_date — ISO date, default today

Graceful degradation: if corporate_actions domain health is failing, returns raw
prices and populates _meta.warnings. Never 503.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query

from backend.clients.jip_equity_service import JIPEquityService
from backend.db.session import async_session_factory
from backend.models.instruments import PriceMeta, PricePoint, PriceResponse
from backend.services.adjustment_service import (
    apply_adjustment,
    compute_adjustment_schedule,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/instruments", tags=["instruments"])

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_HEALTH_PATH = _REPO_ROOT / "data-health.json"
_HEALTH_CACHE: dict[str, tuple[list[str], Any]] = {}
_HEALTH_CACHE_TTL = 60.0


def _check_corporate_actions_health() -> list[str]:
    """Soft health check for corporate_actions domain.

    Returns a list of warning strings. Empty list means health is OK.
    Fail-open: if data-health.json is missing, returns [] (no warnings).
    """
    cached = _HEALTH_CACHE.get("ca_health")
    if cached is not None:
        cached_warnings, ts = cached
        if time.monotonic() - ts < _HEALTH_CACHE_TTL:
            return cached_warnings

    warning_list: list[str] = []
    if not _DATA_HEALTH_PATH.exists():
        _HEALTH_CACHE["ca_health"] = (warning_list, time.monotonic())
        return warning_list

    try:
        raw: Any = json.loads(_DATA_HEALTH_PATH.read_text(encoding="utf-8"))
        tables: list[dict[str, Any]] = raw.get("tables", [])
        failing = [
            t for t in tables if t.get("domain") == "corporate_actions" and not t.get("pass", True)
        ]
        for t in failing:
            warning_list.append(f"adjustment_factor_health_degraded: {t.get('table', 'unknown')}")
    except Exception as exc:
        log.warning("instruments_health_check_error", error=str(exc))

    _HEALTH_CACHE["ca_health"] = (warning_list, time.monotonic())
    return warning_list


@router.get("/{symbol}/price", response_model=None)
async def get_price(
    symbol: str,
    adjusted: bool = Query(True, description="Apply back-adjustment (default true)"),
    from_date: Optional[date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[date] = Query(None, description="End date (inclusive)"),
) -> dict[str, Any]:
    """Return OHLCV price series for a symbol, optionally back-adjusted.

    Back-adjustment uses corporate action factors from de_corporate_actions
    (split/bonus/rights only, dividend-neutral). Historical prices are multiplied
    by the product of all adj_factors for events occurring after each price date.

    When adjustment-factor health is degraded, falls back to raw prices and
    includes a warning in _meta.warnings.
    """
    today = datetime.now(UTC).date()
    resolved_from = from_date or (today - timedelta(days=365))
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

    sym = symbol.upper()

    async with async_session_factory() as session:
        svc = JIPEquityService(session)

        # Verify symbol exists via JIP client (keeps de_* access out of routes)
        if not await svc.symbol_exists(sym):
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "INSTRUMENT_NOT_FOUND",
                        "message": f"No active instrument found for symbol '{sym}'",
                        "details": {},
                    }
                },
            )

        # Fetch raw OHLCV
        raw_prices = await svc.get_chart_data(sym, resolved_from, resolved_to)

        # Determine if we should apply adjustment
        health_warnings: list[str] = []
        use_adjusted = adjusted

        if adjusted:
            health_warnings = _check_corporate_actions_health()
            if health_warnings:
                use_adjusted = False
                log.warning(
                    "instruments_price_degraded_to_raw",
                    symbol=sym,
                    warnings=health_warnings,
                )
            else:
                # Fetch corporate actions and compute schedule
                try:
                    actions = await svc.get_corporate_actions(sym)
                    schedule = compute_adjustment_schedule(actions)
                    raw_prices = apply_adjustment(raw_prices, schedule)
                except Exception as exc:
                    log.error(
                        "instruments_adjustment_failed",
                        symbol=sym,
                        error=str(exc),
                    )
                    health_warnings = [f"adjustment_computation_failed: {type(exc).__name__}"]
                    use_adjusted = False

    # Build response
    price_points: list[PricePoint] = []
    data_as_of: Optional[date] = None
    for price_row in raw_prices:
        row_date: date = price_row["date"]
        if data_as_of is None or row_date > data_as_of:
            data_as_of = row_date
        price_points.append(
            PricePoint(
                trade_date=row_date,
                open=_dec(price_row.get("open")),
                high=_dec(price_row.get("high")),
                low=_dec(price_row.get("low")),
                close=_dec(price_row.get("close")),
                volume=price_row.get("volume"),
                adjusted=use_adjusted,
            )
        )

    meta = PriceMeta(
        symbol=sym,
        from_date=resolved_from,
        to_date=resolved_to,
        adjusted=use_adjusted,
        data_as_of=data_as_of,
        warnings=health_warnings,
        point_count=len(price_points),
    )
    response = PriceResponse(price_series=price_points, meta=meta)
    return response.model_dump(mode="json")


def _dec(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    return Decimal(str(val))
