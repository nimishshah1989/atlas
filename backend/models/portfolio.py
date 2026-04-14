"""Pydantic v2 request/response schemas for the V4 Portfolio Management slice."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# Minimum confidence score to consider a scheme mapped (inclusive)
MAPPING_CONFIDENCE_THRESHOLD = Decimal("0.70")


# --- Enums ---


class PortfolioType(str, Enum):
    cams_import = "cams_import"
    manual = "manual"
    model = "model"


class OwnerType(str, Enum):
    pms = "pms"
    ria_client = "ria_client"
    retail = "retail"


class MappingStatus(str, Enum):
    mapped = "mapped"
    pending = "pending"
    manual_override = "manual_override"


# --- Holding models ---


class HoldingBase(BaseModel):
    """Core holding fields used both in create requests and responses."""

    scheme_name: str = Field(description="Original scheme name from CAMS/broker")
    folio_number: Optional[str] = Field(default=None, description="Folio number if available")
    units: Decimal = Field(description="Number of units held")
    nav: Optional[Decimal] = Field(default=None, description="Latest NAV at import time")
    mstar_id: Optional[str] = Field(default=None, description="Mapped Morningstar identifier")
    mapping_confidence: Optional[Decimal] = Field(
        default=None, description="Fuzzy match confidence score (0-1)"
    )
    mapping_status: MappingStatus = Field(
        default=MappingStatus.pending, description="Current mapping status"
    )


class HoldingResponse(HoldingBase):
    """Full holding response including DB-assigned fields."""

    id: UUID
    portfolio_id: UUID
    current_value: Optional[Decimal] = Field(
        default=None, description="Current value in paise (units * nav)"
    )
    cost_value: Optional[Decimal] = Field(default=None, description="Purchase cost in paise")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Portfolio models ---


class PortfolioBase(BaseModel):
    """Core portfolio fields."""

    name: Optional[str] = Field(default=None, description="Portfolio display name")
    portfolio_type: PortfolioType = Field(description="Type of portfolio")
    owner_type: OwnerType = Field(description="Owner classification")


class PortfolioCreateRequest(PortfolioBase):
    """POST /api/v1/portfolio/create request body."""

    holdings: list[HoldingBase] = Field(
        default_factory=list, description="Initial holdings to import"
    )
    user_id: Optional[str] = Field(default=None, description="User identifier")


class PortfolioResponse(PortfolioBase):
    """Full portfolio response including holdings and metadata."""

    id: UUID
    user_id: Optional[str] = None
    holdings: list[HoldingResponse] = Field(default_factory=list)
    analysis_cache: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PortfolioListResponse(BaseModel):
    """GET /api/v1/portfolio/ response."""

    portfolios: list[PortfolioResponse]
    _meta: dict[str, Any] = {}
    count: int
    data_as_of: datetime


class PortfolioUpdateRequest(BaseModel):
    """PUT /api/v1/portfolio/{id} request body."""

    name: Optional[str] = None
    portfolio_type: Optional[PortfolioType] = None
    owner_type: Optional[OwnerType] = None


# --- Snapshot / analysis models ---


class PortfolioAnalysisResponse(BaseModel):
    """Response for a portfolio snapshot/analysis record (legacy slim version).

    Kept for backward compatibility. New callers should use PortfolioFullAnalysisResponse.
    """

    id: UUID
    portfolio_id: UUID
    snapshot_date: date
    total_value: Decimal = Field(description="Total portfolio value in paise")
    total_cost: Optional[Decimal] = None
    holdings_count: int
    sector_weights: Optional[dict[str, Any]] = None
    quadrant_distribution: Optional[dict[str, Any]] = None
    weighted_rs: Optional[Decimal] = None

    model_config = {"from_attributes": True}


# --- Rich analysis models (V4-3) ---


class AnalysisProvenance(BaseModel):
    """Source table + formula for a computed metric (traceability requirement)."""

    source_table: str = Field(description="JIP de_* table or atlas table this metric comes from")
    formula: str = Field(description="Human-readable formula or derivation")


class HoldingAnalysis(BaseModel):
    """Per-holding analysis combining JIP data with holding weight in portfolio."""

    holding_id: UUID
    mstar_id: str
    scheme_name: str
    units: Decimal
    nav: Optional[Decimal] = Field(default=None, description="Latest NAV from JIP")
    current_value: Optional[Decimal] = Field(
        default=None, description="Current value = units × NAV"
    )
    weight_pct: Optional[Decimal] = Field(
        default=None, description="Holding weight in portfolio (0-100)"
    )

    # Returns from JIP
    return_1m: Optional[Decimal] = None
    return_3m: Optional[Decimal] = None
    return_6m: Optional[Decimal] = None
    return_1y: Optional[Decimal] = None
    return_3y: Optional[Decimal] = None
    return_5y: Optional[Decimal] = None

    # RS / momentum
    rs_composite: Optional[Decimal] = None
    rs_momentum_28d: Optional[Decimal] = None
    quadrant: Optional[str] = None

    # Derived metrics
    sharpe_ratio: Optional[Decimal] = None
    sortino_ratio: Optional[Decimal] = None
    alpha: Optional[Decimal] = None
    beta: Optional[Decimal] = None

    # Weighted technicals
    weighted_rsi: Optional[Decimal] = None
    weighted_breadth_pct_above_200dma: Optional[Decimal] = None
    weighted_macd_bullish_pct: Optional[Decimal] = None

    # Sectors (top 3)
    top_sectors: list[dict[str, Any]] = Field(default_factory=list)

    # Provenance
    provenance: dict[str, AnalysisProvenance] = Field(
        default_factory=dict,
        description="Metric name → source_table + formula for traceability",
    )


class PortfolioLevelAnalysis(BaseModel):
    """Aggregated portfolio-level metrics computed from per-holding JIP data."""

    total_value: Decimal = Field(description="Sum of all holding current_values")
    total_cost: Optional[Decimal] = Field(
        default=None, description="Sum of cost_value across holdings from atlas"
    )
    holdings_count: int
    mapped_count: int = Field(description="Holdings with a valid mstar_id mapping")
    unmapped_count: int = Field(description="Holdings without mstar_id (pending/unresolved)")

    # Weighted RS
    weighted_rs: Optional[Decimal] = Field(
        default=None,
        description="Value-weighted average RS composite across mapped holdings",
    )

    # Sector concentration (sector → aggregated weight_pct across portfolio)
    sector_weights: dict[str, Decimal] = Field(default_factory=dict)

    # Quadrant distribution
    quadrant_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Count of holdings per quadrant (LEADING/LAGGING/IMPROVING/WEAKENING/UNKNOWN)",
    )

    # Weighted averages
    weighted_sharpe: Optional[Decimal] = None
    weighted_sortino: Optional[Decimal] = None
    weighted_beta: Optional[Decimal] = None

    # Fund overlap summary (only computed when ≥2 mapped holdings)
    overlap_pairs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Pairwise overlap between fund pairs (top 5 by overlap_pct)",
    )

    # Provenance
    provenance: dict[str, AnalysisProvenance] = Field(
        default_factory=dict,
        description="Metric name → source_table + formula for traceability",
    )


class PortfolioFullAnalysisResponse(BaseModel):
    """Rich analysis response for GET /{portfolio_id}/analysis.

    Combines per-holding JIP data with portfolio-level aggregations.
    Gracefully degrades: unavailable list records which holdings had JIP fetch failures.
    """

    portfolio_id: UUID
    portfolio_name: Optional[str] = None
    data_as_of: date = Field(description="Date for which analysis is computed")
    computed_at: datetime = Field(description="UTC timestamp when this response was computed")

    holdings: list[HoldingAnalysis] = Field(default_factory=list)
    portfolio: PortfolioLevelAnalysis
    unavailable: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Holdings that could not be enriched with JIP data, with reason",
    )
    rs_data_available: bool = Field(
        default=True,
        description="False when batch RS fetch failed; RS metrics will be None",
    )


# --- Import result models ---


class ParsedHolding(BaseModel):
    """A single holding parsed from a CAS PDF before scheme mapping."""

    scheme_name: str
    folio_number: Optional[str] = None
    units: Decimal
    nav: Optional[Decimal] = None
    value: Optional[Decimal] = None
    mstar_id: Optional[str] = None
    mapping_confidence: Optional[Decimal] = None
    mapping_status: MappingStatus = MappingStatus.pending


class PortfolioImportResult(BaseModel):
    """Response for POST /api/v1/portfolio/import-cams."""

    portfolio_id: UUID
    portfolio_name: Optional[str]
    holdings: list[HoldingResponse]
    needs_review: list[HoldingResponse]
    mapped_count: int
    pending_count: int
    total_count: int
    data_as_of: datetime


# --- Scheme mapping override models ---


class SchemeMappingOverrideCreate(BaseModel):
    """Request to create a scheme mapping override."""

    scheme_name_pattern: str = Field(description="CAMS scheme name to match")
    mstar_id: str = Field(description="Morningstar ID to map to")
    notes: Optional[str] = None
    created_by: Optional[str] = None


class SchemeMappingOverrideResponse(SchemeMappingOverrideCreate):
    """Response for a scheme mapping override record."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
