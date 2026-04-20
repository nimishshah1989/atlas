"""Conviction and screener Pydantic models — C-DER-2.

Split from schemas.py to keep that module under the 500-line modularity budget.
Re-exported via backend.models.schemas for backward compatibility.

NOTE: This module does NOT import from backend.models.schemas to avoid a
circular import. (schemas.py imports from this module at module level.)
ResponseMeta is defined in schemas.py — ScreenerResponse lives in
backend/routes/screener.py where ResponseMeta is imported directly.
"""

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ConvictionScore(BaseModel):
    instrument_id: str
    scope: str
    score: Decimal  # 0..100, 2 decimals
    weight_band: str  # "0%" | "1%" | "3%" | "5%"
    components: dict[str, Decimal]  # keys: "selection", "value", "regime_fit"
    suggested_weight_pct: Decimal  # Decimal("0")|Decimal("1")|Decimal("3")|Decimal("5")
    reason: str


class ConvictionLevel(str, Enum):
    HIGH_PLUS = "HIGH+"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    AVOID = "AVOID"


class ActionSignal(str, Enum):
    BUY = "BUY"
    ACCUMULATE = "ACCUMULATE"
    WATCH = "WATCH"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class UrgencyLevel(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    DEVELOPING = "DEVELOPING"
    PATIENT = "PATIENT"


class FourFactorConviction(BaseModel):
    conviction_level: ConvictionLevel
    action_signal: ActionSignal
    urgency: UrgencyLevel
    factor_returns_rs: bool = False
    factor_momentum_rs: bool = False
    factor_sector_rs: bool = False
    factor_volume_rs: bool = False
    factors_aligned: int = 0
    rs_composite: Optional[Decimal] = None
    roc_21_pct_rank: Optional[Decimal] = None
    sector_rs_composite: Optional[Decimal] = None
    cmf_20: Optional[Decimal] = None
    mfi_14: Optional[Decimal] = None
    regime: Optional[str] = None


class ScreenerRow(BaseModel):
    symbol: str
    company_name: str
    sector: Optional[str] = None
    rs_composite: Optional[Decimal] = None
    rsi_14: Optional[Decimal] = None
    above_50dma: Optional[bool] = None
    above_200dma: Optional[bool] = None
    macd_bullish: Optional[bool] = None
    market_cap_cr: Optional[Decimal] = None
    pe_ratio: Optional[Decimal] = None
    conviction_level: Optional[ConvictionLevel] = None
    action_signal: Optional[ActionSignal] = None
    urgency: Optional[UrgencyLevel] = None
    nifty_50: bool = False
    nifty_500: bool = False
