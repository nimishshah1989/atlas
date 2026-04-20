"""Pydantic v2 models for composite regime (S2 RegimeComposer)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel


class RegimeBand(BaseModel):
    label: str  # "BULL" | "CAUTIOUS" | "CORRECTION" | "BEAR" | "RISK_ON" | "RISK_OFF"
    score: Decimal  # 0-100
    confidence: Decimal  # 0-1
    evidence: list[str] = []


class CompositeRegime(BaseModel):
    posture: str  # "SELECTIVE" | "RISK_ON" | "RISK_OFF"
    confidence: Decimal
    global_band: RegimeBand
    india_band: RegimeBand
    sectors: list[dict[str, Any]] = []
    reason: str
    data_as_of: Optional[datetime.date] = None
