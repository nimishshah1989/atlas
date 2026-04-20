"""Pydantic v2 models for the lens / 4-lens framework (S2 slice)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from backend.services.signal_engine import Signal


class LensValue(BaseModel):
    value: Optional[Decimal] = None
    percentile: Optional[Decimal] = None  # vs universe, 0-100
    signals: list[Signal] = []


class LensBundle(BaseModel):
    scope: str
    entity_id: str
    benchmark: str
    period: str
    lenses: dict[str, LensValue]  # keys: "rs", "momentum", "breadth", "volume"
    composite_action: str  # "BUY" | "HOLD" | "WATCH" | "AVOID" | "SELL"
    data_as_of: Optional[datetime.date] = None
    reason: str
