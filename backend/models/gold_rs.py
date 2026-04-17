"""Gold RS Pydantic v2 models for V7.

Gold RS (Relative Strength vs Gold) measures how an entity (stock, sector,
ETF) has performed relative to the gold benchmark over multiple time windows.

Signal classification follows strict inequality (no zero-boundary ambiguity):
  AMPLIFIES_BULL      — bench > 0 AND rs_gold > 0
  AMPLIFIES_BEAR      — bench < 0 AND rs_gold < 0
  NEUTRAL_BENCH_ONLY  — bench > 0 AND rs_gold < 0
  FRAGILE             — everything else (incl. exact zeros, None inputs)
  STALE               — gold data missing AND age > 2 days
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Signal type literal
# ---------------------------------------------------------------------------

GoldRSSignalType = Literal[
    "AMPLIFIES_BULL",
    "AMPLIFIES_BEAR",
    "NEUTRAL_BENCH_ONLY",
    "FRAGILE",
    "STALE",
]

# Valid signal values — used for runtime validation
_VALID_SIGNALS: frozenset[str] = frozenset(
    {"AMPLIFIES_BULL", "AMPLIFIES_BEAR", "NEUTRAL_BENCH_ONLY", "FRAGILE", "STALE"}
)


# ---------------------------------------------------------------------------
# Period sub-model
# ---------------------------------------------------------------------------


class GoldRSPeriods(BaseModel):
    """RS vs gold for each time period.

    All values are in percentage points (e.g. 2.50 means +2.5pp).
    None means insufficient aligned data — never 0, never NaN.
    """

    rs_vs_gold_1m: Optional[Decimal] = None
    rs_vs_gold_3m: Optional[Decimal] = None
    rs_vs_gold_6m: Optional[Decimal] = None
    rs_vs_gold_12m: Optional[Decimal] = None

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Full result model
# ---------------------------------------------------------------------------


class GoldRSResult(BaseModel):
    """Full gold RS computation result for one entity at one date."""

    entity_type: str
    entity_id: str
    date: date
    periods: GoldRSPeriods
    gold_rs_signal: GoldRSSignalType
    gold_series: str  # e.g. "GLD" or "GOLDBEES"
    is_stale: bool = False

    @field_validator("gold_rs_signal")
    @classmethod
    def signal_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_SIGNALS:
            raise ValueError(f"Invalid gold_rs_signal: {v!r}. Must be one of {_VALID_SIGNALS}")
        return v

    @field_validator("entity_type")
    @classmethod
    def entity_type_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("entity_type must not be empty")
        return v

    @field_validator("entity_id")
    @classmethod
    def entity_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("entity_id must not be empty")
        return v

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Cache entry model (mirrors DB row for serialization)
# ---------------------------------------------------------------------------


class GoldRSCacheEntry(BaseModel):
    """Cache entry schema — mirrors atlas_gold_rs_cache DB row.

    Used for Redis serialization/deserialization and DB upsert boundary.
    All Decimal fields use str(value) round-trip to avoid float intermediary.
    """

    entity_type: str
    entity_id: str
    date: date
    rs_vs_gold_1m: Optional[Decimal] = None
    rs_vs_gold_3m: Optional[Decimal] = None
    rs_vs_gold_6m: Optional[Decimal] = None
    rs_vs_gold_12m: Optional[Decimal] = None
    gold_rs_signal: GoldRSSignalType
    gold_series: str

    @field_validator("gold_rs_signal")
    @classmethod
    def signal_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_SIGNALS:
            raise ValueError(f"Invalid gold_rs_signal: {v!r}")
        return v

    @classmethod
    def from_result(cls, result: GoldRSResult) -> "GoldRSCacheEntry":
        """Convert a GoldRSResult to a cache entry."""
        return cls(
            entity_type=result.entity_type,
            entity_id=result.entity_id,
            date=result.date,
            rs_vs_gold_1m=result.periods.rs_vs_gold_1m,
            rs_vs_gold_3m=result.periods.rs_vs_gold_3m,
            rs_vs_gold_6m=result.periods.rs_vs_gold_6m,
            rs_vs_gold_12m=result.periods.rs_vs_gold_12m,
            gold_rs_signal=result.gold_rs_signal,
            gold_series=result.gold_series,
        )

    model_config = {"arbitrary_types_allowed": True}
