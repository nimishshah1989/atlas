"""Pydantic v2 models for Alerts API (V6-7)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: int
    source: str
    symbol: Optional[str] = None
    instrument_id: Optional[str] = None  # UUID as str
    alert_type: Optional[str] = None
    message: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    rs_at_alert: Optional[Decimal] = None
    quadrant_at_alert: Optional[str] = None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertReadResponse(BaseModel):
    id: int
    is_read: bool
    message: str


class AlertRuleResponse(BaseModel):
    id: int
    alert_type: str
    threshold: Optional[Decimal] = None
    is_active: bool
    created_at: datetime


class AlertRuleCreateRequest(BaseModel):
    alert_type: str
    threshold: Optional[Decimal] = None
