"""Insider + bulk/block deal routes — gated on JIP data health.

GET /api/stocks/{symbol}/insider      — SEBI PIT disclosure trades
GET /api/stocks/{symbol}/bulk-deals   — NSE bulk deals
GET /api/stocks/{symbol}/block-deals  — NSE block deals

All routes perform an inline freshness/row-count check via JIPInsiderService.
Returns 503 {"reason": "..."} when the underlying JIP table is empty or stale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as _date
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query

from backend.clients.jip_insider_service import JIPInsiderService
from backend.db.session import async_session_factory
from backend.models.insider import (
    BlockDealMeta,
    BlockDealPoint,
    BlockDealResponse,
    BulkDealMeta,
    BulkDealPoint,
    BulkDealResponse,
    InsiderMeta,
    InsiderTradePoint,
    InsiderResponse,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/stocks", tags=["insider"])


def _today() -> _date:
    return datetime.now(UTC).date()


@router.get("/{symbol}/insider", response_model=None)
async def get_insider_trades(
    symbol: str,
    from_date: Optional[_date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[_date] = Query(None, description="End date (inclusive)"),
    limit: int = Query(100, ge=1, le=500, description="Max rows (1-500)"),
) -> dict[str, Any]:
    """Return SEBI PIT insider trades for a symbol.

    Source: JIPInsiderService (insider trades).
    Returns 503 when insider data is unavailable/stale.
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
        svc = JIPInsiderService(session)
        healthy, reason = await svc.check_insider_health()
        if not healthy:
            log.warning("insider_trades_health_fail", symbol=symbol, reason=reason)
            raise HTTPException(status_code=503, detail={"reason": reason})

        rows = await svc.get_insider_trades(symbol.upper(), resolved_from, resolved_to, limit)

    points = [
        InsiderTradePoint(
            txn_date=r["txn_date"],
            filing_date=r.get("filing_date"),
            person_name=r.get("person_name"),
            person_category=r.get("person_category"),
            txn_type=r.get("txn_type"),
            qty=int(r["qty"]) if r.get("qty") is not None else None,
            value_inr=(Decimal(str(r["value_inr"])) if r.get("value_inr") is not None else None),
            post_holding_pct=(
                Decimal(str(r["post_holding_pct"]))
                if r.get("post_holding_pct") is not None
                else None
            ),
        )
        for r in rows
    ]
    data_as_of = max((p.txn_date for p in points), default=None)

    return InsiderResponse(
        insider_trades=points,
        meta=InsiderMeta(
            symbol=symbol.upper(),
            from_date=resolved_from,
            to_date=resolved_to,
            data_as_of=data_as_of,
            point_count=len(points),
            limit=limit,
        ),
    ).model_dump(mode="json")


@router.get("/{symbol}/bulk-deals", response_model=None)
async def get_bulk_deals(
    symbol: str,
    from_date: Optional[_date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[_date] = Query(None, description="End date (inclusive)"),
) -> dict[str, Any]:
    """Return NSE bulk deals for a symbol.

    Source: JIPInsiderService (bulk deals).
    Returns 503 when bulk deal data is unavailable/stale.
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
        svc = JIPInsiderService(session)
        healthy, reason = await svc.check_bulk_health()
        if not healthy:
            log.warning("bulk_deals_health_fail", symbol=symbol, reason=reason)
            raise HTTPException(status_code=503, detail={"reason": reason})

        rows = await svc.get_bulk_deals(symbol.upper(), resolved_from, resolved_to)

    points = [
        BulkDealPoint(
            trade_date=r["trade_date"],
            client_name=r.get("client_name"),
            txn_type=r.get("txn_type"),
            qty=int(r["qty"]) if r.get("qty") is not None else None,
            avg_price=(Decimal(str(r["avg_price"])) if r.get("avg_price") is not None else None),
        )
        for r in rows
    ]
    data_as_of = max((p.trade_date for p in points), default=None)

    return BulkDealResponse(
        bulk_deals=points,
        meta=BulkDealMeta(
            symbol=symbol.upper(),
            from_date=resolved_from,
            to_date=resolved_to,
            data_as_of=data_as_of,
            point_count=len(points),
        ),
    ).model_dump(mode="json")


@router.get("/{symbol}/block-deals", response_model=None)
async def get_block_deals(
    symbol: str,
    from_date: Optional[_date] = Query(None, description="Start date (inclusive)"),
    to_date: Optional[_date] = Query(None, description="End date (inclusive)"),
) -> dict[str, Any]:
    """Return NSE block deals for a symbol.

    Source: JIPInsiderService (block deals).
    Returns 503 when block deal data is unavailable/stale.
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
        svc = JIPInsiderService(session)
        healthy, reason = await svc.check_block_health()
        if not healthy:
            log.warning("block_deals_health_fail", symbol=symbol, reason=reason)
            raise HTTPException(status_code=503, detail={"reason": reason})

        rows = await svc.get_block_deals(symbol.upper(), resolved_from, resolved_to)

    points = [
        BlockDealPoint(
            trade_date=r["trade_date"],
            client_name=r.get("client_name"),
            txn_type=r.get("txn_type"),
            qty=int(r["qty"]) if r.get("qty") is not None else None,
            trade_price=(
                Decimal(str(r["trade_price"])) if r.get("trade_price") is not None else None
            ),
        )
        for r in rows
    ]
    data_as_of = max((p.trade_date for p in points), default=None)

    return BlockDealResponse(
        block_deals=points,
        meta=BlockDealMeta(
            symbol=symbol.upper(),
            from_date=resolved_from,
            to_date=resolved_to,
            data_as_of=data_as_of,
            point_count=len(points),
        ),
    ).model_dump(mode="json")
