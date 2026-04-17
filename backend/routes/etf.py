"""
ETF API routes.

All routes conform to spec §17 (UQL), §18 (include system), §20 (API principles).
Error envelope: {error: {code, message, details}}
"""

from __future__ import annotations

import time
from typing import Optional
import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.etf import (
    ETFChartDataResponse,
    ETFChartPoint,
    ETFDetailResponse,
    ETFRSHistoryPoint,
    ETFRSHistoryResponse,
    ETFUniverseResponse,
)
from backend.models.schemas import ResponseMeta
from backend.services.etf_service import (
    VALID_INCLUDES,
    _build_gold_rs_block,
    _build_rs_block,
    _build_technicals_block,
    _fetch_gold_rs_bulk,
    _parse_includes,
    _safe_decimal,
    get_etf_universe,
)
from backend.services.jip_helpers import (
    etf_chart_data,
    etf_rs_history,
    etf_single_master,
    latest_etf_rs,
    latest_etf_technicals,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/etf", tags=["etf"])

VALID_COUNTRIES = {"US", "India", "UK", "HK", "JP"}


@router.get(
    "/universe",
    response_model=ETFUniverseResponse,
    summary="ETF Universe",
    description=(
        "Return all active ETFs filtered by country/benchmark. "
        "Use `include` to add optional blocks: rs, technicals, gold_rs. "
        "Default response shape is always shape-stable regardless of include."
    ),
    responses={
        400: {"description": "Invalid include parameter (INVALID_INCLUDE)"},
        503: {"description": "JIP data unavailable (JIP_UNAVAILABLE)"},
    },
)
async def get_universe(
    country: Optional[str] = Query(None, description="Filter by country: US|India|UK|HK|JP"),
    benchmark: Optional[str] = Query(None, description="Filter by benchmark name"),
    include: Optional[str] = Query(
        None, description="Comma-separated modules: rs,technicals,gold_rs"
    ),
    as_of: Optional[datetime.date] = Query(None, description="Data cutoff date (default: today)"),
    db: AsyncSession = Depends(get_db),
) -> ETFUniverseResponse:
    """
    GET /api/etf/universe

    Returns active ETF list with optional enrichment modules.
    All financial values are Decimal (serialized as strings).
    """
    t0 = time.perf_counter()

    # Validate country
    if country and country not in VALID_COUNTRIES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_COUNTRY",
                    "message": f"Invalid country '{country}'. Valid: {sorted(VALID_COUNTRIES)}",
                    "details": {},
                }
            },
        )

    # Parse and validate includes
    try:
        includes = _parse_includes(include)
    except ValueError as exc:
        invalid = str(exc).replace("INVALID_INCLUDE:", "")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_INCLUDE",
                    "message": (
                        f"Unknown include module(s): {invalid}. Valid: {sorted(VALID_INCLUDES)}"
                    ),
                    "details": {"invalid": invalid.split(",")},
                }
            },
        ) from exc

    # Fetch data — catch DB/network errors and surface as 503
    try:
        rows, cache_hit = await get_etf_universe(
            db,
            country=country,
            benchmark=benchmark,
            includes=includes,
            as_of=as_of,
        )
    except (SQLAlchemyError, OSError, ConnectionError, TimeoutError, RuntimeError) as exc:
        log.error("etf_universe_jip_error", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "JIP_UNAVAILABLE",
                    "message": "JIP data service unavailable",
                    "details": {},
                }
            },
        ) from exc

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    meta = ResponseMeta(
        data_as_of=as_of or datetime.date.today(),
        record_count=len(rows),
        query_ms=int(elapsed_ms),
        stale=False,
        cache_hit=cache_hit,
        includes_loaded=sorted(includes),
    )

    log.info(
        "etf_universe_served",
        count=len(rows),
        cache_hit=cache_hit,
        elapsed_ms=elapsed_ms,
    )
    return ETFUniverseResponse(etf_rows=rows, meta=meta)


# ---------------------------------------------------------------------------
# V7-2: ETF detail + chart-data + rs-history routes
# IMPORTANT: /{ticker}/chart-data and /{ticker}/rs-history MUST be declared
# BEFORE /{ticker} to prevent the path param from shadowing them.
# ---------------------------------------------------------------------------

_MAX_DATE_RANGE_DAYS = 1826  # 5 years


def _validate_date_range(from_date: datetime.date, to_date: datetime.date) -> None:
    """Raise HTTPException for invalid or oversized date ranges."""
    if from_date >= to_date:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_DATE_RANGE",
                    "message": (f"from_date ({from_date}) must be before to_date ({to_date})"),
                    "details": {},
                }
            },
        )
    if (to_date - from_date).days > _MAX_DATE_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "DATE_RANGE_TOO_LARGE",
                    "message": (
                        f"Date range exceeds maximum of {_MAX_DATE_RANGE_DAYS} days. "
                        f"Requested: {(to_date - from_date).days} days."
                    ),
                    "details": {"max_days": _MAX_DATE_RANGE_DAYS},
                }
            },
        )


@router.get(
    "/{ticker}/chart-data",
    response_model=ETFChartDataResponse,
    summary="ETF OHLCV + technicals chart data",
    description=(
        "Returns OHLCV + key technicals for an ETF over a date range. Default: last 365 days."
    ),
    responses={
        400: {"description": "Invalid date range (INVALID_DATE_RANGE or DATE_RANGE_TOO_LARGE)"},
        404: {"description": "ETF not found (ETF_NOT_FOUND)"},
        503: {"description": "JIP unavailable (JIP_UNAVAILABLE)"},
    },
)
async def get_etf_chart_data(
    ticker: str,
    from_date: Optional[datetime.date] = Query(None, alias="from"),
    to_date: Optional[datetime.date] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> ETFChartDataResponse:
    """GET /api/etf/{ticker}/chart-data"""
    t0 = time.perf_counter()
    today = datetime.date.today()
    resolved_to = to_date or today
    resolved_from = from_date or resolved_to.replace(year=resolved_to.year - 1)

    _validate_date_range(resolved_from, resolved_to)

    try:
        master = await etf_single_master(db, ticker)
        if not master:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "ETF_NOT_FOUND",
                        "message": f"ETF '{ticker.upper()}' not found",
                        "details": {},
                    }
                },
            )
        rows = await etf_chart_data(db, ticker, resolved_from, resolved_to)
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError, ConnectionError, TimeoutError, RuntimeError) as exc:
        log.error("etf_chart_data_jip_error", ticker=ticker, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "JIP_UNAVAILABLE",
                    "message": "JIP data service unavailable",
                    "details": {},
                }
            },
        ) from exc

    points = [
        ETFChartPoint(
            date=r["date"],
            open=_safe_decimal(r.get("open")),
            high=_safe_decimal(r.get("high")),
            low=_safe_decimal(r.get("low")),
            close=_safe_decimal(r.get("close")),
            volume=r.get("volume"),
            sma_50=_safe_decimal(r.get("sma_50")),
            sma_200=_safe_decimal(r.get("sma_200")),
            ema_20=_safe_decimal(r.get("ema_20")),
            rsi_14=_safe_decimal(r.get("rsi_14")),
            macd_line=_safe_decimal(r.get("macd_line")),
            macd_signal=_safe_decimal(r.get("macd_signal")),
            macd_histogram=_safe_decimal(r.get("macd_histogram")),
            bollinger_upper=_safe_decimal(r.get("bollinger_upper")),
            bollinger_lower=_safe_decimal(r.get("bollinger_lower")),
            adx_14=_safe_decimal(r.get("adx_14")),
        )
        for r in rows
    ]
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return ETFChartDataResponse(
        ticker=ticker.upper(),
        points=points,
        meta=ResponseMeta(
            data_as_of=resolved_to,
            record_count=len(points),
            query_ms=int(elapsed_ms),
            stale=False,
        ),
    )


@router.get(
    "/{ticker}/rs-history",
    response_model=ETFRSHistoryResponse,
    summary="ETF RS score history",
    description="Returns RS composite+momentum+quadrant time series. Default: 12 months.",
    responses={
        400: {"description": "Invalid months (INVALID_DATE_RANGE)"},
        404: {"description": "ETF not found (ETF_NOT_FOUND)"},
        503: {"description": "JIP unavailable (JIP_UNAVAILABLE)"},
    },
)
async def get_etf_rs_history(
    ticker: str,
    months: Optional[int] = Query(12, description="Lookback in months (1-120)", ge=1, le=120),
    db: AsyncSession = Depends(get_db),
) -> ETFRSHistoryResponse:
    """GET /api/etf/{ticker}/rs-history"""
    t0 = time.perf_counter()
    today = datetime.date.today()
    resolved_months = months if months is not None else 12
    days_back = resolved_months * 30
    from_date = today - datetime.timedelta(days=days_back)
    to_date = today

    try:
        master = await etf_single_master(db, ticker)
        if not master:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "ETF_NOT_FOUND",
                        "message": f"ETF '{ticker.upper()}' not found",
                        "details": {},
                    }
                },
            )
        rows = await etf_rs_history(db, ticker, from_date, to_date)
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError, ConnectionError, TimeoutError, RuntimeError) as exc:
        log.error("etf_rs_history_jip_error", ticker=ticker, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "JIP_UNAVAILABLE",
                    "message": "JIP data service unavailable",
                    "details": {},
                }
            },
        ) from exc

    from backend.models.schemas import Quadrant

    points: list[ETFRSHistoryPoint] = []
    for r in rows:
        quadrant_val = r.get("quadrant")
        quadrant = None
        if quadrant_val:
            try:
                quadrant = Quadrant(str(quadrant_val).upper())
            except ValueError:
                pass
        points.append(
            ETFRSHistoryPoint(
                date=r["date"],
                rs_composite=_safe_decimal(r.get("rs_composite")),
                rs_momentum=_safe_decimal(r.get("rs_momentum")),
                quadrant=quadrant,
            )
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return ETFRSHistoryResponse(
        ticker=ticker.upper(),
        months=resolved_months,
        points=points,
        meta=ResponseMeta(
            data_as_of=to_date,
            record_count=len(points),
            query_ms=int(elapsed_ms),
            stale=False,
        ),
    )


@router.get(
    "/{ticker}",
    response_model=ETFDetailResponse,
    summary="ETF detail",
    description="Full ETF detail: master info + latest RS, technicals, gold_rs blocks.",
    responses={
        404: {"description": "ETF not found (ETF_NOT_FOUND)"},
        503: {"description": "JIP unavailable (JIP_UNAVAILABLE)"},
    },
)
async def get_etf_detail(
    ticker: str,
    as_of: Optional[datetime.date] = Query(None, description="Data cutoff date"),
    db: AsyncSession = Depends(get_db),
) -> ETFDetailResponse:
    """GET /api/etf/{ticker}"""
    t0 = time.perf_counter()
    if as_of is None:
        as_of = datetime.date.today()

    try:
        master = await etf_single_master(db, ticker)
        if not master:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "ETF_NOT_FOUND",
                        "message": f"ETF '{ticker.upper()}' not found",
                        "details": {},
                    }
                },
            )
        tickers = [ticker.upper()]
        tech_rows = await latest_etf_technicals(db, tickers=tickers, as_of=as_of)
        rs_rows = await latest_etf_rs(db, tickers=tickers, as_of=as_of)
        gold_rs_rows = await _fetch_gold_rs_bulk(db, tickers=tickers, as_of=as_of)
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError, ConnectionError, TimeoutError, RuntimeError) as exc:
        log.error("etf_detail_jip_error", ticker=ticker, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "JIP_UNAVAILABLE",
                    "message": "JIP data service unavailable",
                    "details": {},
                }
            },
        ) from exc

    tu = ticker.upper()
    tech_data = tech_rows.get(tu, {})

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return ETFDetailResponse(
        ticker=tu,
        name=master.get("name", ""),
        exchange=master.get("exchange"),
        country=master.get("country", ""),
        currency=master.get("currency", "USD"),
        sector=master.get("sector"),
        asset_class=master.get("asset_class"),
        category=master.get("category"),
        benchmark=master.get("benchmark"),
        expense_ratio=_safe_decimal(master.get("expense_ratio")),
        inception_date=master.get("inception_date"),
        is_active=bool(master.get("is_active", True)),
        last_price=_safe_decimal(tech_data.get("close_price")),
        last_date=tech_data.get("date"),
        rs=_build_rs_block(rs_rows[tu]) if tu in rs_rows else None,
        technicals=_build_technicals_block(tech_data) if tech_data else None,
        gold_rs=_build_gold_rs_block(gold_rs_rows[tu]) if tu in gold_rs_rows else None,
        meta=ResponseMeta(
            data_as_of=as_of,
            record_count=1,
            query_ms=int(elapsed_ms),
            stale=False,
        ),
    )
