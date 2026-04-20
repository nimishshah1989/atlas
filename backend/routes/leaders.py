"""Leaders route — GET /api/v1/leaders.

Thin wrapper over LeadersService. Returns standard envelope.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.schemas import ResponseMeta
from backend.services.lens_service import LeadersService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leaders", tags=["leaders"])


@router.get(
    "/",
    summary="Ranked leaders from a universe",
    description="Returns top-100 instruments ranked by RS composite, with optional aligned filter.",
)
async def get_leaders(
    universe: Optional[str] = Query(default="NIFTY500", description="Universe filter"),
    benchmark: Optional[str] = Query(default="NIFTY 500", description="Benchmark index"),
    period: Optional[str] = Query(default="3M", description="Evaluation period"),
    aligned_only: Optional[bool] = Query(default=True, description="Return aligned leaders only"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    t0 = time.monotonic()
    rows = await LeadersService(session).rank(
        universe=universe or "NIFTY500",
        benchmark=benchmark or "NIFTY 500",
        period=period or "3M",
        aligned_only=aligned_only if aligned_only is not None else True,
    )
    query_ms = int((time.monotonic() - t0) * 1000)
    return {
        "data": {"rows": rows},
        "meta": ResponseMeta(
            record_count=len(rows),
            query_ms=query_ms,
        ).model_dump(),
    }
