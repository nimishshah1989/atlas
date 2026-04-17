"""Sector routes for ATLAS C-DER-3.

Provides:
  GET /api/v1/sectors/rrg — Relative Rotation Graph data for all sectors.

Note: this prefix (/api/v1/sectors) does not collide with the existing
/api/v1/stocks/sectors route which is registered under the stocks router.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.schemas import RRGResponse
from backend.services.rrg_service import compute_sector_rrg

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/sectors", tags=["sectors"])


@router.get("/rrg", response_model=RRGResponse)
async def get_sector_rrg(
    benchmark: Annotated[
        str,
        Query(
            description=(
                "Benchmark index name (placeholder — all sectors returned "
                "regardless; future releases will filter to benchmark constituents)"
            )
        ),
    ] = "NIFTY 50",
    db: AsyncSession = Depends(get_db),
) -> RRGResponse:
    """Return Relative Rotation Graph data for all tracked sectors.

    Response includes normalised RS score (100-centred), RS momentum,
    RRG quadrant, breadth data, and a 4-point weekly historical tail per sector.

    Raises 503 when no sector RS data is available in the database.
    """
    log.info("get_sector_rrg", benchmark=benchmark)
    return await compute_sector_rrg(benchmark=benchmark, db=db)
