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
from backend.models.etf import ETFUniverseResponse
from backend.models.schemas import ResponseMeta
from backend.services.etf_service import VALID_INCLUDES, _parse_includes, get_etf_universe

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
