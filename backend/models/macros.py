"""Pydantic v2 models for macro routes: yield curve, FX rates, RBI policy rates."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, model_serializer


# ---------------------------------------------------------------------------
# Yield curve (de_gsec_yield)
# ---------------------------------------------------------------------------


class YieldPoint(BaseModel):
    tenor: str
    yield_pct: Decimal
    security_name: Optional[str] = None
    source: Optional[str] = None


class YieldCurveEntry(BaseModel):
    yield_date: date
    points: list[YieldPoint]


class YieldCurveMeta(BaseModel):
    from_date: date
    to_date: date
    data_as_of: Optional[date] = None
    date_count: int
    point_count: int


class YieldCurveResponse(BaseModel):
    yield_curve: list[YieldCurveEntry]
    meta: YieldCurveMeta

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "data": [e.model_dump(mode="json") for e in self.yield_curve],
            "_meta": self.meta.model_dump(mode="json"),
        }


# ---------------------------------------------------------------------------
# FX rates (de_rbi_fx_rate)
# ---------------------------------------------------------------------------


class FXPoint(BaseModel):
    rate_date: date
    currency_pair: str
    reference_rate: Decimal
    source: Optional[str] = None


class FXMeta(BaseModel):
    from_date: date
    to_date: date
    currency_pairs: list[str]
    data_as_of: Optional[date] = None
    point_count: int


class FXResponse(BaseModel):
    fx_rates: list[FXPoint]
    meta: FXMeta

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "data": [p.model_dump(mode="json") for p in self.fx_rates],
            "_meta": self.meta.model_dump(mode="json"),
        }


# ---------------------------------------------------------------------------
# RBI policy rates (de_rbi_policy_rate)
# ---------------------------------------------------------------------------


class PolicyRatePoint(BaseModel):
    effective_date: date
    rate_type: str
    rate_pct: Decimal
    source: Optional[str] = None


class PolicyRateMeta(BaseModel):
    from_date: date
    to_date: date
    rate_types: list[str]
    data_as_of: Optional[date] = None
    point_count: int


class PolicyRateResponse(BaseModel):
    policy_rates: list[PolicyRatePoint]
    meta: PolicyRateMeta

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "data": [p.model_dump(mode="json") for p in self.policy_rates],
            "_meta": self.meta.model_dump(mode="json"),
        }
