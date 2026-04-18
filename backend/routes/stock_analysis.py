"""Stock analysis route — V11-9 OpenBB + FinanceToolkit pilot.

GET /api/v1/stocks/{symbol}/analysis?engine=legacy|openbb

Registered via a dedicated router with the same /api/v1/stocks prefix as
stocks.py, which avoids inflating that file beyond the 500-line gate.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.db.session import get_db
from backend.models.analysis import AnalysisMeta, AnalysisResult, LegacySignals, OpenBBSignals
from backend.services.analysis_service import build_legacy_signals, build_openbb_signals

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


@router.get("/{symbol}/analysis")
async def get_stock_analysis(
    symbol: str,
    engine: Optional[str] = Query(
        "legacy",
        description="Analysis engine: 'legacy' (JIP data, default) or 'openbb' (superset pilot)",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Structured signal analysis for a stock.

    Returns a structured signal set for investment analysis.
    The ``engine`` parameter selects the signal provider:

    * **legacy** (default): Minimal structured signals from JIP data.
      Fast, deterministic, always available.
    * **openbb** (pilot): Strict superset of legacy signals, adding
      additional technical and fundamental metrics.
      The pilot is disabled by default; pass ``?engine=openbb`` to opt in.

    The OpenBB engine response always contains all keys that the legacy
    engine returns, plus additional fields. A schema-diff test in the
    test suite enforces this invariant.
    """
    resolved_engine = (engine or "legacy").lower()
    if resolved_engine not in ("legacy", "openbb"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_ENGINE",
                    "message": f"engine must be 'legacy' or 'openbb', got {engine!r}",
                }
            },
        )

    t0 = time.monotonic()
    svc = JIPDataService(db)
    stock_detail = await svc.get_stock_detail(symbol)

    if not stock_detail:
        raise HTTPException(status_code=404, detail=f"Stock {symbol.upper()} not found")

    if resolved_engine == "openbb":
        signals: LegacySignals | OpenBBSignals = await build_openbb_signals(stock_detail, db)
    else:
        signals = build_legacy_signals(stock_detail)

    elapsed = int((time.monotonic() - t0) * 1000)
    analysis_result = AnalysisResult(
        symbol=symbol.upper(),
        engine=resolved_engine,
        signals=signals,
        meta=AnalysisMeta(
            data_as_of=stock_detail.get("rs_date"),
            engine=resolved_engine,
            record_count=1,
            query_ms=elapsed,
        ),
    )
    return analysis_result.model_dump()
