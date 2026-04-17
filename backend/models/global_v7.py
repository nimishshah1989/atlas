"""Pydantic v2 models for V7-3 global routes.

Routes:
  GET /api/global/ratios      — 9 macro series with 10-pt sparkline + MoM change
  GET /api/global/rs-heatmap  — 131 instruments grouped by instrument_type
  GET /api/global/indices     — global indices with four_bench_verdict + gold_rs_signal
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, model_serializer

from backend.models.global_intel import MacroSparkItem  # reuse existing spark model
from backend.models.gold_rs import GoldRSSignalType
from backend.models.schemas import ResponseMeta

_Date = _dt.date


class FourBenchVerdict(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    CAUTION = "CAUTION"
    AVOID = "AVOID"


class MacroRatioV7Item(BaseModel):
    """Macro ratio series with MoM change added."""

    ticker: str
    name: Optional[str] = None
    unit: Optional[str] = None
    latest_value: Optional[Decimal] = None
    latest_date: Optional[_Date] = None
    mom_change: Optional[Decimal] = None  # absolute change vs ~30 trading days ago
    sparkline: list[MacroSparkItem] = []

    model_config = {"arbitrary_types_allowed": True}


class MacroRatiosV7Response(BaseModel):
    """Response for GET /api/global/ratios."""

    ratios: list[MacroRatioV7Item]
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _envelope(self, handler):  # type: ignore[no-untyped-def]
        s = handler(self)
        if "meta" in s:
            s["_meta"] = s["meta"]
        return s

    model_config = {"arbitrary_types_allowed": True}


class GlobalInstrumentEntry(BaseModel):
    """Single row in the RS heatmap — one global instrument."""

    entity_id: str
    name: Optional[str] = None
    instrument_type: Optional[str] = None
    country: Optional[str] = None
    rs_composite: Optional[Decimal] = None
    rs_1m: Optional[Decimal] = None
    rs_3m: Optional[Decimal] = None
    rs_date: Optional[_Date] = None
    close: Optional[Decimal] = None
    price_date: Optional[_Date] = None

    model_config = {"arbitrary_types_allowed": True}


class RSHeatmapGroupedResponse(BaseModel):
    """Response for GET /api/global/rs-heatmap (grouped by instrument_type)."""

    by_type: dict[str, list[GlobalInstrumentEntry]]
    total: int
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _envelope(self, handler):  # type: ignore[no-untyped-def]
        s = handler(self)
        if "meta" in s:
            s["_meta"] = s["meta"]
        return s

    model_config = {"arbitrary_types_allowed": True}


class GlobalIndexRow(BaseModel):
    """Single index row with four_bench_verdict and gold_rs_signal."""

    entity_id: str
    name: Optional[str] = None
    country: Optional[str] = None
    rs_composite: Optional[Decimal] = None
    rs_1m: Optional[Decimal] = None
    rs_3m: Optional[Decimal] = None
    rs_date: Optional[_Date] = None
    close: Optional[Decimal] = None
    price_date: Optional[_Date] = None
    four_bench_verdict: FourBenchVerdict
    gold_rs_signal: Optional[GoldRSSignalType] = None

    model_config = {"arbitrary_types_allowed": True}


class GlobalIndicesResponse(BaseModel):
    """Response for GET /api/global/indices."""

    indices: list[GlobalIndexRow]
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _envelope(self, handler):  # type: ignore[no-untyped-def]
        s = handler(self)
        if "meta" in s:
            s["_meta"] = s["meta"]
        return s

    model_config = {"arbitrary_types_allowed": True}
