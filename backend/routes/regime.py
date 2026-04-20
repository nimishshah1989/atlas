"""Regime route — GET /api/v1/regime.

Thin wrapper over RegimeComposer. Returns standard envelope.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.schemas import ResponseMeta
from backend.services.regime_service import RegimeComposer

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/regime", tags=["regime"])


@router.get(
    "/",
    summary="Get composite market regime",
    description="Composes global + India + sector bands into a single posture.",
)
async def get_regime(
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    t0 = time.monotonic()
    composite = await RegimeComposer(session).compose()
    query_ms = int((time.monotonic() - t0) * 1000)
    return {
        "data": composite.model_dump(),
        "meta": ResponseMeta(
            record_count=1,
            data_as_of=composite.data_as_of,
            query_ms=query_ms,
        ).model_dump(),
    }
