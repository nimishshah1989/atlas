"""Analysis engine models — V11-9."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, model_serializer

from backend.models.schemas import Quadrant


class LegacySignals(BaseModel):
    """Structured signals from JIP data (legacy engine)."""

    rs_composite: Optional[Decimal] = None
    rs_momentum: Optional[Decimal] = None
    rs_quadrant: Optional[Quadrant] = None
    rsi_14: Optional[Decimal] = None
    adx_14: Optional[Decimal] = None
    macd_bullish: Optional[bool] = None
    above_200dma: Optional[bool] = None
    above_50dma: Optional[bool] = None


class OpenBBSignals(LegacySignals):
    """Strict superset of LegacySignals with additional computed metrics (openbb engine)."""

    volatility_20d: Optional[Decimal] = None
    beta_nifty: Optional[Decimal] = None
    sharpe_1y: Optional[Decimal] = None
    sortino_1y: Optional[Decimal] = None
    max_drawdown_1y: Optional[Decimal] = None
    piotroski_score: Optional[int] = None
    macd_line: Optional[Decimal] = None
    macd_signal_line: Optional[Decimal] = None
    bollinger_upper: Optional[Decimal] = None
    bollinger_lower: Optional[Decimal] = None
    stochastic_k: Optional[Decimal] = None
    stochastic_d: Optional[Decimal] = None
    disparity_20: Optional[Decimal] = None


class AnalysisMeta(BaseModel):
    data_as_of: Optional[Any] = None
    engine: str = "legacy"
    record_count: int = 1
    query_ms: int = 0


class AnalysisResult(BaseModel):
    """Single-entity analysis result with engine metadata."""

    symbol: str
    engine: str
    signals: LegacySignals | OpenBBSignals
    meta: AnalysisMeta = Field(default_factory=AnalysisMeta)

    @model_serializer(mode="wrap")
    def _wrap(self, handler: Any) -> dict[str, Any]:
        d = handler(self)
        meta = d.pop("meta", {})
        return {"data": {k: v for k, v in d.items()}, "_meta": meta}
