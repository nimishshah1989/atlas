"""Pydantic v2 models for derivatives (F&O) and macro/VIX routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, model_serializer


class PCRPoint(BaseModel):
    trade_date: date
    pcr_oi: Optional[Decimal] = None
    pcr_volume: Optional[Decimal] = None
    total_oi: Optional[int] = None


class PCRMeta(BaseModel):
    symbol: str
    from_date: date
    to_date: date
    data_as_of: Optional[date] = None
    data_source: str  # "fo_summary" | "fo_bhavcopy_computed"
    point_count: int


class PCRResponse(BaseModel):
    data: list[PCRPoint]
    meta: PCRMeta

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "data": [p.model_dump(mode="json") for p in self.data],
            "_meta": self.meta.model_dump(mode="json"),
        }


class OIPoint(BaseModel):
    trade_date: date
    option_type: Optional[str] = None
    total_oi: int
    change_in_oi: int


class OIMeta(BaseModel):
    symbol: str
    from_date: date
    to_date: date
    data_as_of: Optional[date] = None
    point_count: int


class OIResponse(BaseModel):
    data: list[OIPoint]
    meta: OIMeta

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "data": [p.model_dump(mode="json") for p in self.data],
            "_meta": self.meta.model_dump(mode="json"),
        }


class VIXPoint(BaseModel):
    trade_date: date
    close: Decimal


class VIXMeta(BaseModel):
    ticker: str
    from_date: date
    to_date: date
    data_as_of: Optional[date] = None
    point_count: int


class VIXResponse(BaseModel):
    data: list[VIXPoint]
    meta: VIXMeta

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "data": [p.model_dump(mode="json") for p in self.data],
            "_meta": self.meta.model_dump(mode="json"),
        }
