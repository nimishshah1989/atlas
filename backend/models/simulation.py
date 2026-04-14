"""Pydantic v2 request/response schemas for the V3 Simulation Engine."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- Enums ---


class SignalType(str, Enum):
    BREADTH = "breadth"
    MCCLELLAN = "mcclellan"
    RS = "rs"
    PE = "pe"
    REGIME = "regime"
    SECTOR_RS = "sector_rs"
    MCCLELLAN_SUMMATION = "mcclellan_summation"
    COMBINED = "combined"


class CombineLogic(str, Enum):
    AND = "AND"
    OR = "OR"


class TransactionAction(str, Enum):
    SIP_BUY = "sip_buy"
    LUMPSUM_BUY = "lumpsum_buy"
    SELL = "sell"
    REDEPLOY = "redeploy"


# --- Config models ---


class SimulationParameters(BaseModel):
    """User-configurable simulation parameters (spec §8)."""

    sip_amount: Decimal = Field(default=Decimal("10000"), description="Monthly SIP amount in INR")
    lumpsum_amount: Decimal = Field(
        default=Decimal("50000"), description="Lumpsum deployment amount in INR"
    )
    buy_level: Decimal = Field(description="Signal threshold for entry")
    sell_level: Decimal = Field(description="Signal threshold for exit")
    reentry_level: Optional[Decimal] = Field(
        default=None, description="Signal threshold for re-entry"
    )
    sell_pct: Decimal = Field(
        default=Decimal("100"), description="Percentage to sell at sell_level"
    )
    redeploy_pct: Decimal = Field(
        default=Decimal("100"), description="Percentage of liquid to redeploy"
    )
    cooldown_days: int = Field(default=30, description="Days between lumpsums")


class CombinedSignalConfig(BaseModel):
    """Config for combined (AND/OR) signal mode."""

    signal_a: SignalType
    signal_b: SignalType
    logic: CombineLogic = CombineLogic.AND


class SimulationConfig(BaseModel):
    """Full simulation configuration (spec §8 INPUT)."""

    signal: SignalType
    instrument: str = Field(description="Stock symbol, MF mstar_id, or basket name")
    instrument_type: str = Field(default="equity", description="equity | mf | etf | basket")
    parameters: SimulationParameters
    start_date: date
    end_date: date
    combined_config: Optional[CombinedSignalConfig] = None


# --- Result models ---


class SimulationSummary(BaseModel):
    """Top-level KPI summary (spec §8 OUTPUT.summary)."""

    total_invested: Decimal
    final_value: Decimal
    xirr: Decimal
    cagr: Decimal
    vs_plain_sip: Decimal
    vs_benchmark: Decimal
    alpha: Decimal
    max_drawdown: Decimal
    sharpe: Decimal
    sortino: Decimal


class TaxDetail(BaseModel):
    """Per-transaction tax breakdown."""

    stcg_tax: Decimal = Decimal("0")
    ltcg_tax: Decimal = Decimal("0")
    cess: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")


class TaxSummary(BaseModel):
    """Aggregate tax across the simulation (spec §8 OUTPUT.tax_summary)."""

    stcg: Decimal
    ltcg: Decimal
    total_tax: Decimal
    post_tax_xirr: Decimal
    unrealized: Decimal


class TransactionRecord(BaseModel):
    """Single transaction in the simulation log (spec §8 OUTPUT.transactions)."""

    date: date
    action: TransactionAction
    amount: Decimal
    nav: Decimal
    units: Decimal
    tax_detail: Optional[TaxDetail] = None


class DailyValue(BaseModel):
    """Daily portfolio snapshot (spec §8 OUTPUT.daily_values)."""

    date: date
    nav: Decimal
    units: Decimal
    fv: Decimal
    liquid: Decimal
    total: Decimal


class SimulationResult(BaseModel):
    """Complete simulation output."""

    summary: SimulationSummary
    daily_values: list[DailyValue]
    transactions: list[TransactionRecord]
    tax_summary: TaxSummary
    tear_sheet_url: Optional[str] = None
    data_as_of: datetime


# --- Request/Response ---


class SimulationRunRequest(BaseModel):
    """POST /api/v1/simulate/run request body."""

    config: SimulationConfig


class SimulationRunResponse(BaseModel):
    """POST /api/v1/simulate/run response."""

    result: SimulationResult
    data_as_of: datetime
    staleness: str = Field(description="FRESH | STALE | EXPIRED")


class SimulationListItem(BaseModel):
    """Summary for listing saved simulations."""

    id: UUID
    name: Optional[str] = None
    config: SimulationConfig
    created_at: datetime
    is_auto_loop: bool = False


class SimulationListResponse(BaseModel):
    """GET /api/v1/simulate/ response."""

    simulations: list[SimulationListItem]
    count: int
