"""Pydantic v2 response models for ATLAS V2 MF (mutual fund) API.

Contracts mirror `specs/001-mf-slice/contracts/mf-api.md`. All numeric
financial fields are `Decimal` (serialised as strings); every top-level
response carries `data_as_of` + `staleness`. Decimal-only — no IEEE-754.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.schemas import Quadrant


class StalenessFlag(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    EXPIRED = "EXPIRED"


class Staleness(BaseModel):
    source: str
    age_minutes: int = Field(ge=0)
    flag: StalenessFlag = StalenessFlag.FRESH


# --- /universe -------------------------------------------------------------


class Fund(BaseModel):
    mstar_id: str
    fund_name: str
    amc_name: str
    category_name: str
    broad_category: str
    nav: Optional[Decimal] = None
    nav_date: Optional[date] = None
    rs_composite: Optional[Decimal] = None
    rs_momentum_28d: Optional[Decimal] = None
    quadrant: Optional[Quadrant] = None
    manager_alpha: Optional[Decimal] = None
    expense_ratio: Optional[Decimal] = None
    is_index_fund: bool = False
    primary_benchmark: Optional[str] = None


class CategoryGroup(BaseModel):
    name: str
    funds: list[Fund] = []


class BroadCategoryGroup(BaseModel):
    name: str
    categories: list[CategoryGroup] = []


class UniverseResponse(BaseModel):
    broad_categories: list[BroadCategoryGroup] = []
    data_as_of: date
    staleness: Staleness


# --- /categories -----------------------------------------------------------


class CategoryRow(BaseModel):
    category_name: str
    broad_category: str
    fund_count: int = 0
    avg_rs_composite: Optional[Decimal] = None
    quadrant_distribution: dict[str, int] = {}
    net_flow_cr: Optional[Decimal] = None
    sip_flow_cr: Optional[Decimal] = None
    total_aum_cr: Optional[Decimal] = None
    manager_alpha_p50: Optional[Decimal] = None
    manager_alpha_p90: Optional[Decimal] = None


class CategoriesResponse(BaseModel):
    categories: list[CategoryRow] = []
    data_as_of: date
    staleness: Staleness


# --- /flows ----------------------------------------------------------------


class FlowRow(BaseModel):
    month_date: date
    category: str
    net_flow_cr: Optional[Decimal] = None
    gross_inflow_cr: Optional[Decimal] = None
    gross_outflow_cr: Optional[Decimal] = None
    aum_cr: Optional[Decimal] = None
    sip_flow_cr: Optional[Decimal] = None
    sip_accounts: Optional[int] = None
    folios: Optional[int] = None


class FlowsResponse(BaseModel):
    flows: list[FlowRow] = []
    data_as_of: date
    staleness: Staleness


# --- /{mstar_id} (deep dive) ----------------------------------------------


class FundIdentity(BaseModel):
    mstar_id: str
    fund_name: str
    amc_name: str
    category_name: str
    broad_category: str
    primary_benchmark: Optional[str] = None
    inception_date: Optional[date] = None
    is_index_fund: bool = False


class FundDailyMetrics(BaseModel):
    nav: Optional[Decimal] = None
    nav_date: Optional[date] = None
    aum_cr: Optional[Decimal] = None
    expense_ratio: Optional[Decimal] = None
    return_1m: Optional[Decimal] = None
    return_3m: Optional[Decimal] = None
    return_6m: Optional[Decimal] = None
    return_1y: Optional[Decimal] = None
    return_3y: Optional[Decimal] = None
    return_5y: Optional[Decimal] = None


class PillarPerformance(BaseModel):
    manager_alpha: Optional[Decimal] = None
    information_ratio: Optional[Decimal] = None
    capture_up: Optional[Decimal] = None
    capture_down: Optional[Decimal] = None
    explanation: str = ""


class PillarRSStrength(BaseModel):
    rs_composite: Optional[Decimal] = None
    rs_momentum_28d: Optional[Decimal] = None
    quadrant: Optional[Quadrant] = None
    explanation: str = ""


class PillarFlows(BaseModel):
    net_flow_cr_3m: Optional[Decimal] = None
    sip_flow_cr_3m: Optional[Decimal] = None
    folio_growth_pct: Optional[Decimal] = None
    explanation: str = ""


class PillarHoldingsQuality(BaseModel):
    holdings_avg_rs: Optional[Decimal] = None
    pct_above_200dma: Optional[Decimal] = None
    concentration_top10_pct: Optional[Decimal] = None
    explanation: str = ""


class ConvictionPillarsMF(BaseModel):
    performance: PillarPerformance
    rs_strength: PillarRSStrength
    flows: PillarFlows
    holdings_quality: PillarHoldingsQuality


class SectorExposureSummary(BaseModel):
    top_sector: Optional[str] = None
    top_sector_weight_pct: Optional[Decimal] = None
    sector_count: int = 0


class TopHoldingSummary(BaseModel):
    symbol: str
    holding_name: str
    weight_pct: Decimal


class WeightedTechnicalsSummary(BaseModel):
    weighted_rsi: Optional[Decimal] = None
    weighted_breadth_pct_above_200dma: Optional[Decimal] = None
    weighted_macd_bullish_pct: Optional[Decimal] = None
    as_of_date: Optional[date] = None


class MFLifecycleEvent(BaseModel):
    event_type: str
    effective_date: date
    detail: Optional[str] = None


class FundDeepDiveResponse(BaseModel):
    identity: FundIdentity
    daily: FundDailyMetrics
    pillars: ConvictionPillarsMF
    sector_exposure: SectorExposureSummary
    top_holdings: list[TopHoldingSummary] = []
    weighted_technicals: WeightedTechnicalsSummary
    data_as_of: date
    staleness: Staleness
    inactive: Optional[bool] = None
    mf_lifecycle_event: Optional[MFLifecycleEvent] = None


# --- /{mstar_id}/holdings --------------------------------------------------


class Holding(BaseModel):
    instrument_id: str
    symbol: str
    holding_name: str
    weight_pct: Decimal
    shares_held: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    sector: Optional[str] = None
    rs_composite: Optional[Decimal] = None
    above_200dma: Optional[bool] = None


class HoldingsResponse(BaseModel):
    holdings: list[Holding] = []
    as_of_date: date
    coverage_pct: Decimal
    warnings: list[str] = []


# --- /{mstar_id}/sectors ---------------------------------------------------


class FundSector(BaseModel):
    sector: str
    weight_pct: Decimal
    stock_count: int = 0
    sector_rs_composite: Optional[Decimal] = None


class FundSectorsResponse(BaseModel):
    sectors: list[FundSector] = []
    as_of_date: date


# --- /{mstar_id}/rs-history ------------------------------------------------


class RSHistoryPoint(BaseModel):
    as_of_date: date
    rs_composite: Decimal


class FundRSHistoryResponse(BaseModel):
    mstar_id: str
    points: list[RSHistoryPoint] = []
    data_as_of: date
    staleness: Staleness


# --- /{mstar_id}/weighted-technicals ---------------------------------------


class WeightedTechnicalsResponse(BaseModel):
    mstar_id: str
    weighted_rsi: Optional[Decimal] = None
    weighted_breadth_pct_above_200dma: Optional[Decimal] = None
    weighted_macd_bullish_pct: Optional[Decimal] = None
    as_of_date: date
    data_as_of: date
    staleness: Staleness


# --- /{mstar_id}/nav-history -----------------------------------------------


class NAVPoint(BaseModel):
    nav_date: date
    nav: Decimal


class NAVHistoryResponse(BaseModel):
    mstar_id: str
    points: list[NAVPoint] = []
    coverage_gap_days: int = 0
    data_as_of: date
    staleness: Staleness


# --- /overlap --------------------------------------------------------------


class OverlapHolding(BaseModel):
    instrument_id: str
    symbol: str
    weight_a: Decimal
    weight_b: Decimal


class OverlapResponse(BaseModel):
    fund_a: str
    fund_b: str
    overlap_pct: Decimal
    common_holdings: list[OverlapHolding] = []
    data_as_of: date
    staleness: Staleness


# --- /holding-stock/{symbol} -----------------------------------------------


class FundHoldingStockEntry(BaseModel):
    mstar_id: str
    fund_name: str
    weight_pct: Decimal


class HoldingStockResponse(BaseModel):
    symbol: str
    instrument_id: Optional[str] = None
    funds: list[FundHoldingStockEntry] = []
    data_as_of: date
    staleness: Staleness
