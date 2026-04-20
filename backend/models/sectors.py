"""Pydantic v2 models for sector aggregation (S2 slice)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel

from backend.services.signal_engine import Signal


class SectorSummary(BaseModel):
    key: str
    universe: str
    four_lens: dict[str, Optional[Decimal]]  # "rs", "momentum", "breadth", "volume"
    signals: list[Signal] = []
    composite_action: str = "HOLD"
    stocks: list[dict[str, Any]] = []
    mfs: list[dict[str, Any]] = []
    etfs: list[dict[str, Any]] = []
    data_as_of: Optional[datetime.date] = None
