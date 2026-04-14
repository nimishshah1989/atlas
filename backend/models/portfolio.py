"""Pydantic v2 request/response schemas for the V4 Portfolio Management slice."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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
    """Response for a portfolio snapshot/analysis record."""

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
