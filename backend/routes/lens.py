"""Lens route — GET /api/v1/lens/{scope}/{entity_id}.

Thin wrapper over LensService. Returns standard envelope.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.schemas import ResponseMeta
from backend.services.lens_service import LensService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/lens", tags=["lens"])


@router.get(
    "/{scope}/{entity_id}",
    summary="Get 4-lens bundle for a scope/entity",
    description="Returns RS, momentum, breadth, volume lenses + signals for any instrument.",
)
async def get_lens(
    scope: str,
    entity_id: str,
    benchmark: Optional[str] = Query(default="NIFTY 500", description="Benchmark index"),
    period: Optional[str] = Query(default="3M", description="Evaluation period"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        bundle = await LensService(session).get_lenses(
            scope=scope,
            entity_id=entity_id,
            benchmark=benchmark or "NIFTY 500",
            period=period or "3M",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    query_ms = int((time.monotonic() - t0) * 1000)
    return {
        "data": bundle.model_dump(),
        "meta": ResponseMeta(
            record_count=len(bundle.lenses),
            data_as_of=bundle.data_as_of,
            query_ms=query_ms,
        ).model_dump(),
    }
