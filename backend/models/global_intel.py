"""Pydantic v2 request/response schemas for Global Intelligence API (V5-9)."""

import datetime as _dt
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, model_serializer

from backend.models.schemas import ResponseMeta

# Use the fully-qualified datetime.date so that fields named 'date' do not
# shadow the type annotation — Pydantic v2 uses the enclosing namespace when
# resolving type hints, and `date: Optional[date]` collapses to `None`-only.
_Date = _dt.date
_Datetime = _dt.datetime


# --- Briefing ---


class BriefingDetail(BaseModel):
    """A single market briefing from atlas_briefings."""

    id: int
    date: _Date
    scope: str
    scope_key: Optional[str] = None
    headline: str
    narrative: str
    key_signals: Optional[Any] = None
    theses: Optional[Any] = None
    patterns: Optional[Any] = None
    india_implication: Optional[str] = None
    risk_scenario: Optional[str] = None
    conviction: Optional[str] = None
    model_used: Optional[str] = None
    staleness_flags: Optional[dict[str, Any]] = None
    generated_at: _Datetime


class BriefingResponse(BaseModel):
    """Response for GET /global/briefing.

    Returns the latest briefing (or null data when table is empty).
    Emits both ``data`` (§20.4 standard) and ``briefing`` (V1 compat).
    ``_meta`` mirrors ``meta``.
    """

    briefing: Optional[BriefingDetail] = None
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_envelope(self, handler):  # type: ignore[no-untyped-def]
        serialized = handler(self)
        serialized["data"] = serialized.get("briefing")
        if "meta" in serialized:
            serialized["_meta"] = serialized["meta"]
        return serialized


# --- Macro Ratios ---


class MacroSparkItem(BaseModel):
    """One data point in a sparkline series."""

    date: _Date
    value: Optional[Decimal] = None


class MacroRatioItem(BaseModel):
    """A single macro series with its latest value and sparkline."""

    ticker: str
    name: Optional[str] = None
    unit: Optional[str] = None
    latest_value: Optional[Decimal] = None
    latest_date: Optional[_Date] = None
    sparkline: list[MacroSparkItem] = []


class MacroRatiosResponse(BaseModel):
    """Response for GET /global/ratios.

    Emits ``data`` (§20.4) and ``ratios`` (V1 compat). ``_meta`` mirrors ``meta``.
    """

    ratios: list[MacroRatioItem]
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_envelope(self, handler):  # type: ignore[no-untyped-def]
        serialized = handler(self)
        if "ratios" in serialized:
            serialized["data"] = serialized["ratios"]
        if "meta" in serialized:
            serialized["_meta"] = serialized["meta"]
        return serialized


# --- RS Heatmap ---


class GlobalRSEntry(BaseModel):
    """One row in the global RS heatmap."""

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


class RSHeatmapResponse(BaseModel):
    """Response for GET /global/rs-heatmap.

    Emits ``data`` (§20.4) and ``heatmap`` (V1 compat). ``_meta`` mirrors ``meta``.
    """

    heatmap: list[GlobalRSEntry]
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_envelope(self, handler):  # type: ignore[no-untyped-def]
        serialized = handler(self)
        if "heatmap" in serialized:
            serialized["data"] = serialized["heatmap"]
        if "meta" in serialized:
            serialized["_meta"] = serialized["meta"]
        return serialized


# --- Regime ---


class RegimeSummary(BaseModel):
    """Regime data from de_market_regime."""

    date: Optional[_Date] = None
    regime: Optional[str] = None
    confidence: Optional[Decimal] = None
    breadth_score: Optional[Decimal] = None
    momentum_score: Optional[Decimal] = None
    volume_score: Optional[Decimal] = None
    global_score: Optional[Decimal] = None
    fii_score: Optional[Decimal] = None


class BreadthSummary(BaseModel):
    """Breadth data from de_breadth_daily."""

    date: Optional[_Date] = None
    advance: Optional[int] = None
    decline: Optional[int] = None
    unchanged: Optional[int] = None
    total_stocks: Optional[int] = None
    ad_ratio: Optional[Decimal] = None
    pct_above_200dma: Optional[Decimal] = None
    pct_above_50dma: Optional[Decimal] = None
    new_52w_highs: Optional[int] = None
    new_52w_lows: Optional[int] = None


class GlobalRegimeResponse(BaseModel):
    """Response for GET /global/regime.

    Emits ``data`` (§20.4) containing both regime + breadth, plus ``_meta``.
    """

    regime: Optional[RegimeSummary] = None
    breadth: Optional[BreadthSummary] = None
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_envelope(self, handler):  # type: ignore[no-untyped-def]
        serialized = handler(self)
        # §20.4: data key must be present
        serialized["data"] = {
            "regime": serialized.get("regime"),
            "breadth": serialized.get("breadth"),
        }
        if "meta" in serialized:
            serialized["_meta"] = serialized["meta"]
        return serialized


# --- Patterns ---


class PatternFinding(BaseModel):
    """One inter-market pattern finding from atlas_intelligence."""

    id: UUID
    finding_type: str
    title: str
    content: str
    entity: Optional[str] = None
    entity_type: Optional[str] = None
    confidence: Optional[Decimal] = None
    tags: Optional[list[str]] = None
    data_as_of: _Datetime
    created_at: _Datetime


class GlobalPatternsResponse(BaseModel):
    """Response for GET /global/patterns.

    Emits ``data`` (§20.4) and ``patterns`` (V1 compat). ``_meta`` mirrors ``meta``.
    """

    patterns: list[PatternFinding]
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_envelope(self, handler):  # type: ignore[no-untyped-def]
        serialized = handler(self)
        if "patterns" in serialized:
            serialized["data"] = serialized["patterns"]
        if "meta" in serialized:
            serialized["_meta"] = serialized["meta"]
        return serialized
