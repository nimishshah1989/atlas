"""Book route — GET /api/v1/book.

Returns portfolio holdings, watchlist, action queue, and performance
as a single composite response. All four BookService methods called.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.schemas import ResponseMeta
from backend.services.book_service import BookService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/book", tags=["book"])


def _default(obj: Any) -> Any:
    """JSON serializer helper for Decimal values."""
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@router.get(
    "/",
    summary="Get portfolio book (holdings + watchlist + action queue + performance)",
    description="Aggregates holdings, watchlist, actionable items, and performance totals.",
)
async def get_book(
    portfolio_id: Optional[uuid.UUID] = Query(default=None, description="Portfolio UUID filter"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    t0 = time.monotonic()
    svc = BookService(session)

    holdings = await svc.holdings(portfolio_id=portfolio_id)
    watchlist = await svc.watchlist()
    action_queue = await svc.action_queue(portfolio_id=portfolio_id)
    performance = await svc.performance(portfolio_id=portfolio_id)

    # Normalise Decimal to str for JSON response
    def _dec_to_str(v: Any) -> Any:
        if isinstance(v, Decimal):
            return str(v)
        return v

    perf_serialisable = {k: _dec_to_str(v) for k, v in performance.items()}

    query_ms = int((time.monotonic() - t0) * 1000)
    return {
        "data": {
            "holdings": holdings,
            "watchlist": watchlist,
            "action_queue": action_queue,
            "performance": perf_serialisable,
        },
        "meta": ResponseMeta(
            record_count=len(holdings),
            query_ms=query_ms,
        ).model_dump(),
    }
