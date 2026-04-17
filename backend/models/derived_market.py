"""Pydantic v2 models for C-DER-3 market data derived signals.

Contains:
  - RegimeTransition: historical regime transition record
  - SentimentZone: 5-level sentiment classification enum
  - SentimentComponent: single weighted component of the sentiment composite
  - SentimentResponse: full sentiment composite response
  - RRGPoint: single weekly point in an RRG sector tail
  - RRGSector: one sector's RRG data (score, momentum, quadrant, tail)
  - RRGResponse: full RRG response for all sectors

NOTE: This module does NOT import from backend.models.schemas to avoid a
circular import. (schemas.py imports from this module at module level via
a late import at the bottom of the file.)

ResponseMeta and Quadrant are re-imported here using TYPE_CHECKING only,
so at runtime these resolve through the existing module cache without
triggering a fresh module load that would cause the cycle.

Callers should import these models from backend.models.schemas (re-exported)
or directly from this module.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    pass  # Quadrant and ResponseMeta resolved at runtime via Any to avoid cycles


# ---------------------------------------------------------------------------
# Regime enrichment models
# ---------------------------------------------------------------------------


class RegimeTransition(BaseModel):
    """A completed regime transition (historical, not the current open segment)."""

    regime: str
    started_date: date
    ended_date: Optional[date] = None  # None = current regime (open)
    duration_days: int
    breadth_pct_at_start: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# Sentiment models
# ---------------------------------------------------------------------------


class SentimentZone(str, Enum):
    EXTREME_FEAR = "EXTREME_FEAR"
    FEAR = "FEAR"
    NEUTRAL = "NEUTRAL"
    GREED = "GREED"
    EXTREME_GREED = "EXTREME_GREED"


class SentimentComponent(BaseModel):
    name: str
    score: Optional[Decimal] = None  # 0–100, None when unavailable
    weight: Decimal  # effective weight after redistribution
    available: bool = True
    note: Optional[str] = None


class SentimentResponse(BaseModel):
    composite_score: Optional[Decimal] = None  # 0–100 weighted average
    zone: Optional[SentimentZone] = None
    components: list[SentimentComponent]
    weight_redistribution_active: bool = False
    as_of: Optional[date] = None
    meta: Any  # ResponseMeta at runtime; Any used to break TYPE_CHECKING cycle


# ---------------------------------------------------------------------------
# RRG models
# ---------------------------------------------------------------------------


class RRGPoint(BaseModel):
    """Single weekly data point in the 4-point tail of a sector RRG."""

    date: date
    rs_score: Decimal  # normalised, 100-centred
    rs_momentum: Decimal


class RRGSector(BaseModel):
    sector: str
    rs_score: Decimal  # (rs_raw - mean) / stddev * 10 + 100
    rs_momentum: Decimal  # rs_composite_today - rs_composite_28d_ago
    quadrant: Any  # Quadrant enum at runtime; Any used to break TYPE_CHECKING cycle
    pct_above_50dma: Optional[Decimal] = None
    breadth_regime: Optional[str] = None
    tail: list[RRGPoint] = []  # up to 4 weekly points


class RRGResponse(BaseModel):
    sectors: list[RRGSector]
    mean_rs: Decimal
    stddev_rs: Decimal
    as_of: date
    meta: Any  # ResponseMeta at runtime; Any used to break TYPE_CHECKING cycle
