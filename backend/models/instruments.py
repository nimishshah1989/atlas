"""Pydantic v2 models for the instruments price route."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, model_serializer


class PricePoint(BaseModel):
    """Single OHLCV data point."""

    trade_date: date
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Optional[Decimal] = None
    volume: Optional[int] = None
    adjusted: bool


class PriceMeta(BaseModel):
    """Response metadata for price route."""

    symbol: str
    from_date: date
    to_date: date
    adjusted: bool
    data_as_of: Optional[date] = None
    warnings: list[str] = []
    point_count: int


class PriceResponse(BaseModel):
    """§20.4 envelope: data + _meta."""

    price_series: list[PricePoint]
    meta: PriceMeta

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            "data": [p.model_dump() for p in self.price_series],
            "_meta": self.meta.model_dump(),
        }
