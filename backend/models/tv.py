"""Pydantic v2 models for TradingView cache data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TvDataType:
    TA_SUMMARY = "ta_summary"
    FUNDAMENTALS = "fundamentals"
    SCREENER = "screener"


class TvCacheEntry(BaseModel):
    """A single cached TV data entry."""

    symbol: str
    exchange: str = "NSE"
    data_type: str  # 'ta_summary', 'fundamentals', 'screener'
    interval: str = "none"  # '1D', '1W', '1M', or 'none'
    tv_data: dict[str, Any]
    fetched_at: datetime
    is_stale: bool = Field(default=False, description="True if fetched_at > 15 minutes ago")


class TvCacheUpsertRequest(BaseModel):
    """Request to store or update a TV cache entry."""

    symbol: str
    exchange: str = "NSE"
    data_type: str
    interval: str = "none"
    tv_data: dict[str, Any]


# ---------------------------------------------------------------------------
# API response models for GET /api/tv/* routes (V6-4)
# ---------------------------------------------------------------------------


class TvTaData(BaseModel):
    """Parsed TradingView TA summary fields."""

    symbol: str
    exchange: str
    interval: str
    recommendation_1d: Optional[str] = None
    oscillator_score: Optional[str] = None
    ma_score: Optional[str] = None
    buy: Optional[int] = None
    sell: Optional[int] = None
    neutral: Optional[int] = None


class TvScreenerData(BaseModel):
    """Pass-through screener data from TradingView."""

    symbol: str
    exchange: str
    raw: dict[str, Any]


class TvFundamentalsData(BaseModel):
    """Pass-through fundamentals data from TradingView."""

    symbol: str
    exchange: str
    raw: dict[str, Any]
