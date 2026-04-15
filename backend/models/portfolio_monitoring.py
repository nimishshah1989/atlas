"""Pydantic v2 models for V4-6 portfolio monitoring and tax harvesting.

Split from portfolio.py to stay within file-size quality gate.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.models.portfolio import AnalysisProvenance


# --- Monitoring models (V4-6) ---


class MonitoringAlertType(str, Enum):
    RS_DECLINING = "RS_DECLINING"
    LAGGING_HOLDING = "LAGGING_HOLDING"
    SECTOR_CONCENTRATION = "SECTOR_CONCENTRATION"
    FLOW_NEGATIVE = "FLOW_NEGATIVE"
    TAX_HARVEST_OPPORTUNITY = "TAX_HARVEST_OPPORTUNITY"


class MonitoringAlert(BaseModel):
    """A single monitoring alert produced by the daily monitoring service."""

    alert_type: MonitoringAlertType
    severity: str = Field(description="HIGH or CRITICAL")
    metric_name: str = Field(description="The metric that triggered this alert")
    current_value: Decimal = Field(description="Current metric value")
    threshold: Decimal = Field(description="Threshold that was breached")
    holding_id: Optional[UUID] = Field(
        default=None, description="Holding UUID if alert is holding-specific"
    )
    message: str = Field(description="Human-readable alert description")
    provenance: AnalysisProvenance = Field(description="Source and formula for the metric")


class MonitoringThresholds(BaseModel):
    """Configurable thresholds for the daily monitoring engine."""

    rs_decline_pct: Decimal = Field(
        default=Decimal("5"),
        description="Portfolio RS drop > this % from recent peak triggers alert",
    )
    lagging_consecutive_days: int = Field(
        default=28,
        description="Trading days a holding stays LAGGING before rebalancing signal fires",
    )
    sector_concentration_pct: Decimal = Field(
        default=Decimal("40"),
        description="Single-sector portfolio weight > this % triggers alert",
    )
    min_harvest_loss: Decimal = Field(
        default=Decimal("10000"),
        description="Minimum unrealized loss in INR to flag as harvest opportunity",
    )


# --- Tax harvest models (V4-6) ---


class TaxHarvestLot(BaseModel):
    """Per-lot detail for a tax harvest opportunity."""

    buy_date: date
    units: Decimal
    cost_per_unit: Decimal
    current_price: Decimal
    unrealized_gain: Decimal = Field(description="Negative for a loss lot")
    holding_days: int
    is_ltcg: bool = Field(description="True if holding period > 365 days")
    potential_saving: Decimal = Field(description="Estimated tax saving from harvesting this lot")


class TaxHarvestOpportunity(BaseModel):
    """A single holding with harvestable tax losses."""

    holding_id: UUID
    mstar_id: str
    scheme_name: str
    unrealized_loss: Decimal = Field(description="Total unrealized loss (positive number in INR)")
    potential_stcg_saving: Decimal = Field(description="Potential tax saving on STCG losses")
    potential_ltcg_saving: Decimal = Field(description="Potential tax saving on LTCG losses")
    total_potential_saving: Decimal = Field(description="Sum of STCG + LTCG saving")
    lots: list[TaxHarvestLot] = Field(
        default_factory=list, description="FIFO lot breakdown for this holding"
    )
    provenance: AnalysisProvenance


class TaxHarvestSummary(BaseModel):
    """Aggregate tax harvesting summary for a portfolio."""

    opportunities: list[TaxHarvestOpportunity] = Field(default_factory=list)
    total_harvestable_loss: Decimal = Field(
        description="Sum of unrealized_loss across all opportunities"
    )
    total_potential_saving: Decimal = Field(
        description="Sum of total_potential_saving across all opportunities"
    )
    data_as_of: date
    computed_at: datetime


# --- Portfolio monitoring response (V4-6) ---


class PortfolioMonitoringResponse(BaseModel):
    """Combined daily monitoring response: alerts + tax harvest summary."""

    portfolio_id: UUID
    portfolio_name: Optional[str] = None
    data_as_of: date
    computed_at: datetime
    alerts: list[MonitoringAlert] = Field(default_factory=list)
    tax_harvest: Optional[TaxHarvestSummary] = None
    is_trading_day: bool = Field(
        default=True,
        description="False when data_as_of is a non-trading day; alerts will be empty",
    )
