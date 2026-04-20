"""Sector lens route — GET /api/v1/sector/{key}.

Thin wrapper over SectorService. Uses /api/v1/sector prefix to avoid
collision with existing /api/v1/sectors (sectors.py).
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.schemas import ResponseMeta
from backend.services.sector_service import SectorService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/sector", tags=["sector"])


@router.get(
    "/{key}",
    summary="Get sector 4-lens roll-up",
    description="Aggregates constituent stock data into sector RS/momentum/breadth/volume.",
)
async def get_sector_lens(
    key: str,
    universe: Optional[str] = Query(default="NIFTY500", description="Universe filter"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        summary = await SectorService.from_session(session).sector_roll_up(
            key=key,
            universe=universe or "NIFTY500",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    query_ms = int((time.monotonic() - t0) * 1000)
    return {
        "data": summary.model_dump(),
        "meta": ResponseMeta(
            record_count=len(summary.stocks or []),
            data_as_of=summary.data_as_of,
            query_ms=query_ms,
        ).model_dump(),
    }
