"""Stock detail sub-routes — fundamentals and corporate actions.

Split from stocks.py to keep that file under 500 lines (modularity gate).
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


@router.get("/{symbol}/fundamentals", response_model=None)
async def get_stock_fundamentals(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return latest fundamentals snapshot for a stock.

    Source: de_equity_fundamentals JOIN de_instrument.
    Returns insufficient_data=True if data is unavailable.
    """
    t0 = time.monotonic()
    sym = symbol.upper()

    try:
        qr = await db.execute(
            _text("""
                SELECT
                    ef.as_of_date,
                    ef.market_cap_cr,
                    ef.pe_ratio,
                    ef.pb_ratio,
                    ef.peg_ratio,
                    ef.ev_ebitda,
                    ef.roe_pct,
                    ef.roce_pct,
                    ef.operating_margin_pct,
                    ef.net_margin_pct,
                    ef.debt_to_equity,
                    ef.interest_coverage,
                    ef.eps_ttm,
                    ef.book_value,
                    ef.dividend_yield_pct,
                    ef.promoter_holding_pct,
                    ef.pledged_pct,
                    ef.fii_holding_pct,
                    ef.dii_holding_pct,
                    ef.revenue_growth_yoy_pct,
                    ef.profit_growth_yoy_pct,
                    ef.high_52w,
                    ef.low_52w,
                    ef.face_value
                FROM de_equity_fundamentals ef
                JOIN de_instrument i ON ef.instrument_id = i.id
                WHERE (i.symbol = :sym OR i.current_symbol = :sym)
                ORDER BY ef.as_of_date DESC
                LIMIT 1
            """),
            {"sym": sym},
        )
        row = qr.mappings().fetchone()
    except Exception as exc:
        log.warning("fundamentals_query_error", symbol=sym, error=str(exc)[:300])
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "data": None,
            "_meta": {
                "symbol": sym,
                "data_as_of": None,
                "insufficient_data": True,
                "query_ms": elapsed,
                "reason": "fundamentals query failed",
            },
        }

    elapsed = int((time.monotonic() - t0) * 1000)

    if not row:
        return {
            "data": None,
            "_meta": {
                "symbol": sym,
                "data_as_of": None,
                "insufficient_data": True,
                "query_ms": elapsed,
                "reason": f"no fundamentals data for {sym}",
            },
        }

    d = dict(row)
    as_of = d.pop("as_of_date", None)

    def _s(v: Any) -> Any:
        if isinstance(v, Decimal):
            return str(v)
        return v

    return {
        "data": {k: _s(v) for k, v in d.items()},
        "_meta": {
            "symbol": sym,
            "data_as_of": as_of.isoformat() if as_of else None,
            "insufficient_data": False,
            "query_ms": elapsed,
        },
    }


@router.get("/{symbol}/corporate-actions", response_model=None)
async def get_corporate_actions(
    symbol: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return recent corporate actions for a stock.

    Source: de_corporate_actions JOIN de_instrument.
    Returns empty list if no data.
    """
    t0 = time.monotonic()
    sym = symbol.upper()

    try:
        qr = await db.execute(
            _text("""
                SELECT DISTINCT ON (ca.ex_date, ca.action_type)
                    ca.ex_date,
                    ca.action_type,
                    ca.dividend_type,
                    ca.ratio_from,
                    ca.ratio_to,
                    ca.cash_value,
                    ca.notes
                FROM de_corporate_actions ca
                JOIN de_instrument i ON ca.instrument_id = i.id
                WHERE (i.symbol = :sym OR i.current_symbol = :sym)
                ORDER BY ca.ex_date DESC, ca.action_type ASC
                LIMIT :limit
            """),
            {"sym": sym, "limit": limit},
        )
        rows = qr.mappings().all()
    except Exception as exc:
        log.warning("corporate_actions_query_error", symbol=sym, error=str(exc)[:300])
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "data": [],
            "_meta": {
                "symbol": sym,
                "data_as_of": None,
                "insufficient_data": True,
                "query_ms": elapsed,
                "reason": "corporate actions query failed",
            },
        }

    elapsed = int((time.monotonic() - t0) * 1000)

    def _s(v: Any) -> Any:
        if isinstance(v, Decimal):
            return str(v)
        return v

    actions = []
    for r in rows:
        d = dict(r)
        ex_date = d.get("ex_date")
        actions.append(
            {
                "ex_date": ex_date.isoformat() if ex_date else None,
                "action_type": d.get("action_type"),
                "dividend_type": d.get("dividend_type"),
                "ratio_from": _s(d.get("ratio_from")),
                "ratio_to": _s(d.get("ratio_to")),
                "cash_value": _s(d.get("cash_value")),
                "notes": d.get("notes"),
            }
        )

    max_date = actions[0]["ex_date"] if actions else None
    return {
        "data": actions,
        "_meta": {
            "symbol": sym,
            "data_as_of": max_date,
            "insufficient_data": len(actions) == 0,
            "record_count": len(actions),
            "query_ms": elapsed,
        },
    }
