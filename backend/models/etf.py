"""ETF API response models -- Pydantic v2."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional
import datetime

from pydantic import BaseModel, model_serializer

from backend.models.schemas import Quadrant, ResponseMeta


# ---------------------------------------------------------------------------
# Sub-blocks (opt-in via include=)
# ---------------------------------------------------------------------------

GoldRSSignal = Literal["AMPLIFIES_BULL", "AMPLIFIES_BEAR", "NEUTRAL_BENCH_ONLY", "FRAGILE", "STALE"]

GoldSeries = Literal["MCX_INR", "LBMA_USD"]


class ETFGoldRSBlock(BaseModel):
    """Gold RS enrichment block -- opt-in via include=gold_rs."""

    rs_1m: Optional[Decimal] = None
    rs_3m: Optional[Decimal] = None
    rs_6m: Optional[Decimal] = None
    rs_12m: Optional[Decimal] = None
    signal: GoldRSSignal = "STALE"
    gold_series: GoldSeries = "LBMA_USD"
    computed_at: Optional[datetime.datetime] = None
    data_gap: bool = False


class ETFRSBlock(BaseModel):
    """RS enrichment block -- opt-in via include=rs."""

    rs_composite: Optional[Decimal] = None
    rs_momentum: Optional[Decimal] = None
    quadrant: Optional[Quadrant] = None


class ETFTechnicals(BaseModel):
    """24-field technical indicators block -- opt-in via include=technicals."""

    date: Optional[datetime.date] = None
    close_price: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    rsi_14: Optional[Decimal] = None
    macd: Optional[Decimal] = None
    macd_signal: Optional[Decimal] = None
    macd_hist: Optional[Decimal] = None
    bb_upper: Optional[Decimal] = None
    bb_middle: Optional[Decimal] = None
    bb_lower: Optional[Decimal] = None
    bb_width: Optional[Decimal] = None
    sma_20: Optional[Decimal] = None
    sma_50: Optional[Decimal] = None
    sma_200: Optional[Decimal] = None
    ema_9: Optional[Decimal] = None
    ema_21: Optional[Decimal] = None
    adx_14: Optional[Decimal] = None
    di_plus: Optional[Decimal] = None
    di_minus: Optional[Decimal] = None
    stoch_k: Optional[Decimal] = None
    stoch_d: Optional[Decimal] = None
    atr_14: Optional[Decimal] = None
    obv: Optional[Decimal] = None
    vwap: Optional[Decimal] = None
    mom_10: Optional[Decimal] = None
    roc_10: Optional[Decimal] = None
    cci_20: Optional[Decimal] = None
    wpr_14: Optional[Decimal] = None
    cmf_20: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# Core ETF universe row -- always returned (default shape, shape-stable)
# ---------------------------------------------------------------------------


class ETFUniverseRow(BaseModel):
    """Single ETF row in universe response. Core fields always present."""

    ticker: str
    name: str
    country: str
    currency: str
    sector: Optional[str] = None
    category: Optional[str] = None
    benchmark: Optional[str] = None
    expense_ratio: Optional[Decimal] = None
    inception_date: Optional[datetime.date] = None
    is_active: bool = True
    last_price: Optional[Decimal] = None
    last_date: Optional[datetime.date] = None
    # opt-in blocks
    rs: Optional[ETFRSBlock] = None
    technicals: Optional[ETFTechnicals] = None
    gold_rs: Optional[ETFGoldRSBlock] = None


# ---------------------------------------------------------------------------
# Universe response envelope
# ---------------------------------------------------------------------------


class ETFUniverseResponse(BaseModel):
    """ETF universe response envelope.

    Serializes ``data`` and ``_meta`` (spec §20.4 standard shape).
    Field ``etf_rows`` serializes to ``data`` in JSON output via model_serializer.
    """

    etf_rows: list[ETFUniverseRow]
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_envelope(self, handler: Any) -> Any:
        serialized = handler(self)
        # Rename internal field to standard API key
        if "etf_rows" in serialized:
            serialized["data"] = serialized.pop("etf_rows")
        if "meta" in serialized:
            serialized["_meta"] = serialized.pop("meta")
        return serialized
