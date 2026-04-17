"""Pydantic v2 request/response schemas for ATLAS V1 API."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, model_serializer


# --- Enums ---


class Quadrant(str, Enum):
    LEADING = "LEADING"
    IMPROVING = "IMPROVING"
    WEAKENING = "WEAKENING"
    LAGGING = "LAGGING"


class Regime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    RECOVERY = "RECOVERY"


class DecisionAction(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    IGNORED = "IGNORED"
    OVERRIDDEN = "OVERRIDDEN"


class DecisionSignal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WATCH = "WATCH"
    # Spec §23.2 decision types (lowercase to match DB values written by decisions-generator)
    BUY_SIGNAL = "buy_signal"
    SELL_SIGNAL = "sell_signal"
    OVERWEIGHT = "overweight"
    AVOID = "avoid"
    ROTATION = "rotation"
    REBALANCE = "rebalance"
    REDUCE_EQUITY = "reduce_equity"


class UQLOperator(str, Enum):
    EQ = "="
    NEQ = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"
    CONTAINS = "contains"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


# --- Meta ---


class ResponseMeta(BaseModel):
    """Response provenance + pagination meta.

    V1 fields (data_as_of/record_count/query_ms/stale) remain present and
    typed identically for backward compatibility (spec §SC-003). The
    additional fields below are populated by `services.uql.meta.build_meta`
    for V2 UQL responses; V1 fixed-endpoint callers leave them as defaults.
    """

    data_as_of: Optional[date] = None
    record_count: int = 0
    query_ms: Optional[int] = None
    stale: bool = False

    # V2 UQL additive fields (spec §17 / data-model §4)
    returned: Optional[int] = None
    total_count: Optional[int] = None
    offset: Optional[int] = None
    limit: Optional[int] = None
    has_more: Optional[bool] = None
    next_offset: Optional[int] = None
    cache_hit: Optional[bool] = None
    includes_loaded: Optional[list[str]] = None
    staleness: Optional[Literal["fresh", "stale", "unknown"]] = None
    partial_data: bool = False


# --- Stock Models ---


class StockSummary(BaseModel):
    id: UUID
    symbol: str
    company_name: str
    sector: Optional[str] = None
    nifty_50: bool = False
    nifty_200: bool = False
    nifty_500: bool = False
    close: Optional[Decimal] = None
    rs_composite: Optional[Decimal] = None
    rs_momentum: Optional[Decimal] = None
    quadrant: Optional[Quadrant] = None
    rsi_14: Optional[Decimal] = None
    adx_14: Optional[Decimal] = None
    above_200dma: Optional[bool] = None
    above_50dma: Optional[bool] = None
    macd_histogram: Optional[Decimal] = None
    beta_nifty: Optional[Decimal] = None
    sharpe_1y: Optional[Decimal] = None
    mf_holder_count: Optional[int] = None
    cap_category: Optional[str] = None


class SectorGroup(BaseModel):
    sector: str
    stock_count: int
    stocks: list[StockSummary]


class StockUniverseResponse(BaseModel):
    sectors: list[SectorGroup]
    meta: ResponseMeta


# --- Sector Models ---


class SectorMetrics(BaseModel):
    sector: str
    stock_count: int
    # RS
    avg_rs_composite: Optional[Decimal] = None
    avg_rs_momentum: Optional[Decimal] = None
    sector_quadrant: Optional[Quadrant] = None
    # Breadth
    pct_above_200dma: Optional[Decimal] = None
    pct_above_50dma: Optional[Decimal] = None
    pct_above_ema21: Optional[Decimal] = None
    # Momentum
    avg_rsi_14: Optional[Decimal] = None
    pct_rsi_overbought: Optional[Decimal] = None
    pct_rsi_oversold: Optional[Decimal] = None
    # Trend
    avg_adx: Optional[Decimal] = None
    pct_adx_trending: Optional[Decimal] = None
    pct_macd_bullish: Optional[Decimal] = None
    pct_roc5_positive: Optional[Decimal] = None
    # Risk
    avg_beta: Optional[Decimal] = None
    avg_sharpe: Optional[Decimal] = None
    avg_sortino: Optional[Decimal] = None
    avg_volatility_20d: Optional[Decimal] = None
    avg_max_dd: Optional[Decimal] = None
    avg_calmar: Optional[Decimal] = None
    # Institutional
    avg_mf_holders: Optional[Decimal] = None
    # Disparity
    avg_disparity_20: Optional[Decimal] = None


class SectorListResponse(BaseModel):
    sectors: list[SectorMetrics]
    meta: ResponseMeta


# --- Conviction Pillars ---


class PillarRS(BaseModel):
    rs_composite: Optional[Decimal] = None
    rs_momentum: Optional[Decimal] = None
    rs_1w: Optional[Decimal] = None
    rs_1m: Optional[Decimal] = None
    rs_3m: Optional[Decimal] = None
    rs_6m: Optional[Decimal] = None
    rs_12m: Optional[Decimal] = None
    quadrant: Optional[Quadrant] = None
    benchmark: str = "NIFTY 500"
    explanation: str = ""


class TechnicalCheck(BaseModel):
    name: str
    passing: bool
    value: Optional[str] = None
    detail: str = ""


class PillarTechnical(BaseModel):
    checks_passing: int = 0
    checks_total: int = 10
    checks: list[TechnicalCheck] = []
    explanation: str = ""


class PillarInstitutional(BaseModel):
    mf_holder_count: Optional[int] = None
    delivery_vs_avg: Optional[Decimal] = None
    explanation: str = ""


class PillarExternal(BaseModel):
    """Pillar 3: External confirmation via TradingView TA data."""

    tv_ta: Optional[dict[str, Any]] = None
    explanation: str = ""


class ConvictionPillars(BaseModel):
    rs: PillarRS
    technical: PillarTechnical
    institutional: PillarInstitutional
    pillar_3: Optional[PillarExternal] = None


from backend.models.derived import GoldRS, GoldRSSignal, Piotroski, PiotroskiDetail  # noqa: E402, F401
from backend.models.conviction import ActionSignal, ConvictionLevel, FourFactorConviction, ScreenerRow, UrgencyLevel  # noqa: E402, E501, F401  # fmt: skip


# --- Deep Dive ---


class StockDeepDive(BaseModel):
    id: UUID
    symbol: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    nifty_50: bool = False
    nifty_200: bool = False
    nifty_500: bool = False
    isin: Optional[str] = None
    listing_date: Optional[date] = None
    cap_category: Optional[str] = None
    # Price
    close: Optional[Decimal] = None
    # Full technicals
    sma_50: Optional[Decimal] = None
    sma_200: Optional[Decimal] = None
    ema_20: Optional[Decimal] = None
    rsi_14: Optional[Decimal] = None
    adx_14: Optional[Decimal] = None
    macd_line: Optional[Decimal] = None
    macd_signal: Optional[Decimal] = None
    macd_histogram: Optional[Decimal] = None
    above_200dma: Optional[bool] = None
    above_50dma: Optional[bool] = None
    beta_nifty: Optional[Decimal] = None
    sharpe_1y: Optional[Decimal] = None
    sortino_1y: Optional[Decimal] = None
    max_drawdown_1y: Optional[Decimal] = None
    calmar_ratio: Optional[Decimal] = None
    volatility_20d: Optional[Decimal] = None
    relative_volume: Optional[Decimal] = None
    mfi_14: Optional[Decimal] = None
    obv: Optional[int] = None
    delivery_vs_avg: Optional[Decimal] = None
    bollinger_upper: Optional[Decimal] = None
    bollinger_lower: Optional[Decimal] = None
    disparity_20: Optional[Decimal] = None
    stochastic_k: Optional[Decimal] = None
    stochastic_d: Optional[Decimal] = None
    # Conviction
    conviction: ConvictionPillars
    # Institutional
    mf_holder_count: Optional[int] = None
    # Derived signals (query-time, fault-tolerant)
    gold_rs: Optional[GoldRS] = None
    piotroski: Optional[Piotroski] = None
    four_factor: Optional[FourFactorConviction] = None


class StockDeepDiveResponse(BaseModel):
    """Single-equity deep-dive response (spec §17.10 + §18.2).

    Serializes both ``meta`` (V1 contract — frontend reads) and ``_meta``
    (the §18 standard path that ``check-api-standard.py`` asserts via
    ``uql-04-include-system``). Both keys point at the same payload so a
    response is loud about which fields are include-attached without
    breaking V1 consumers.
    """

    stock: StockDeepDive
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_dual_meta(self, handler):  # type: ignore[no-untyped-def]
        serialized = handler(self)
        if "meta" in serialized:
            serialized["_meta"] = serialized["meta"]
        return serialized


# --- Breadth ---


class BreadthSnapshot(BaseModel):
    date: date
    advance: int
    decline: int
    unchanged: int
    total_stocks: int
    ad_ratio: Optional[Decimal] = None
    pct_above_200dma: Optional[Decimal] = None
    pct_above_50dma: Optional[Decimal] = None
    new_52w_highs: int = 0
    new_52w_lows: int = 0
    mcclellan_oscillator: Optional[Decimal] = None
    mcclellan_summation: Optional[Decimal] = None


class RegimeSnapshot(BaseModel):
    date: date
    regime: Regime
    confidence: Optional[Decimal] = None
    breadth_score: Optional[Decimal] = None
    momentum_score: Optional[Decimal] = None
    volume_score: Optional[Decimal] = None
    global_score: Optional[Decimal] = None
    fii_score: Optional[Decimal] = None
    days_in_regime: Optional[int] = None
    regime_history: list[Any] = []  # list[RegimeTransition] — type alias to avoid circular import


class MarketBreadthResponse(BaseModel):
    breadth: BreadthSnapshot
    regime: RegimeSnapshot
    meta: ResponseMeta


# --- RS History ---


class RSDataPoint(BaseModel):
    date: date
    rs_composite: Optional[Decimal] = None
    rs_1w: Optional[Decimal] = None
    rs_1m: Optional[Decimal] = None
    rs_3m: Optional[Decimal] = None


class RSHistoryResponse(BaseModel):
    symbol: str
    benchmark: str
    points: list[RSDataPoint]
    meta: ResponseMeta


# --- Chart Data ---


class ChartDataPoint(BaseModel):
    """Single OHLCV + technical indicator data point for charting."""

    date: date
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Optional[Decimal] = None
    volume: Optional[int] = None
    sma_20: Optional[Decimal] = None
    sma_50: Optional[Decimal] = None
    sma_200: Optional[Decimal] = None
    ema_20: Optional[Decimal] = None
    rsi_14: Optional[Decimal] = None
    macd_histogram: Optional[Decimal] = None


class ChartDataResponse(BaseModel):
    symbol: str
    points: list[ChartDataPoint]
    meta: ResponseMeta


# --- Movers ---


class MoverEntry(BaseModel):
    symbol: str
    company_name: str
    sector: Optional[str] = None
    rs_composite: Optional[Decimal] = None
    rs_momentum: Optional[Decimal] = None
    quadrant: Optional[Quadrant] = None


class MoversResponse(BaseModel):
    gainers: list[MoverEntry]
    losers: list[MoverEntry]
    meta: ResponseMeta


# --- Decisions ---


class DecisionSummary(BaseModel):
    id: UUID
    entity: str
    entity_type: str = "equity"
    decision_type: DecisionSignal
    rationale: str
    confidence: Decimal
    horizon: str
    horizon_end_date: date
    status: str = "active"
    source_agent: Optional[str] = None
    created_at: datetime
    user_action: Optional[DecisionAction] = None
    user_action_at: Optional[datetime] = None
    user_notes: Optional[str] = None


class DecisionActionRequest(BaseModel):
    action: DecisionAction
    note: Optional[str] = None


class DecisionListResponse(BaseModel):
    decisions: list[DecisionSummary]
    meta: ResponseMeta


# --- UQL Query ---
# UQL v2 schemas live in backend.models.uql (split out to keep this module under the
# 500-line modularity budget). Re-exported below so existing imports keep working.

# --- Intelligence models live in backend.models.intelligence ---
# Callers should import directly from backend.models.intelligence.

# --- Status ---


class DataFreshness(BaseModel):
    equity_ohlcv_as_of: Optional[date] = None
    rs_scores_as_of: Optional[date] = None
    technicals_as_of: Optional[date] = None
    breadth_as_of: Optional[date] = None
    regime_as_of: Optional[date] = None
    mf_holdings_as_of: Optional[date] = None


class StatusResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    freshness: DataFreshness
    active_stocks: int = 0
    sectors: int = 0


# Re-export UQL v2 schemas so callers can keep importing from this module.
from backend.models.uql import (  # noqa: E402, F401
    UQLAggregation,
    UQLAggregationFunction,
    UQLEntityType,
    UQLFilter,
    UQLGranularity,
    UQLIncludeModule,
    UQLMode,
    UQLRequest,
    UQLResponse,
    UQLSort,
    UQLTimeRange,
)

# Re-export C-DER-3 models (kept in derived_market.py for line-budget compliance).
from backend.models.derived_market import (  # noqa: E402, F401
    RegimeTransition,
    RRGPoint,
    RRGResponse,
    RRGSector,
    SentimentComponent,
    SentimentResponse,
    SentimentZone,
)

# fmt: off
__all__ = [
    "GoldRS", "GoldRSSignal", "Piotroski", "PiotroskiDetail",
    "RegimeTransition", "RRGPoint", "RRGResponse", "RRGSector",
    "SentimentComponent", "SentimentResponse", "SentimentZone",
    "UQLAggregation", "UQLAggregationFunction", "UQLEntityType", "UQLFilter",
    "UQLGranularity", "UQLIncludeModule", "UQLMode", "UQLRequest",
    "UQLResponse", "UQLSort", "UQLTimeRange",
]
# fmt: on
