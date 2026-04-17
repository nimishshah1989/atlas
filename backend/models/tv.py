"""Pydantic v2 models for TradingView cache data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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
