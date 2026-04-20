"""Conviction route — POST /api/v1/conviction/score.

Thin wrapper over ConvictionService. Returns standard envelope.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.schemas import ResponseMeta
from backend.services.conviction_service import ConvictionService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/conviction", tags=["conviction"])


class ConvictionScoreRequest(BaseModel):
    instrument_id: str
    scope: str


@router.post(
    "/score",
    summary="Compute conviction score for an instrument",
    description="Returns weighted score (selection + value + regime_fit) and suggested weight.",
)
async def post_conviction_score(
    body: ConvictionScoreRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        conviction = await ConvictionService(session).score(
            instrument_id=body.instrument_id,
            scope=body.scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    query_ms = int((time.monotonic() - t0) * 1000)
    return {
        "data": conviction.model_dump(),
        "meta": ResponseMeta(
            record_count=1,
            query_ms=query_ms,
        ).model_dump(),
    }
