"""Sentiment routes for ATLAS C-DER-3.

Provides:
  GET /api/v1/sentiment/composite — 0–100 composite market sentiment score.

The composite is built from 4 components (Price Breadth, Options/PCR,
Institutional Flow, Fundamental Revisions). Components with unavailable data
are marked unavailable and their weights redistributed to active components.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.schemas import SentimentResponse
from backend.services.sentiment_service import compute_sentiment_composite

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/sentiment", tags=["sentiment"])


@router.get("/composite", response_model=SentimentResponse)
async def get_sentiment_composite(
    db: AsyncSession = Depends(get_db),
) -> SentimentResponse:
    """Return a 0–100 composite sentiment score built from 4 market components.

    Components:
      - Price Breadth (base weight 0.4): derived from market breadth metrics
      - Options/PCR (base weight 0.2): put/call ratio (may be unavailable)
      - Institutional Flow (base weight 0.2): FII flow signals (may be unavailable)
      - Fundamental Revisions (base weight 0.2): median earnings growth metrics

    Weight redistribution is applied automatically when components are unavailable.

    Raises 503 when Price Breadth data is empty — all other component failures
    degrade gracefully to available=False.
    """
    log.info("get_sentiment_composite")
    return await compute_sentiment_composite(db=db)
