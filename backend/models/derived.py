"""Derived signal Pydantic models — Gold RS + Piotroski (C-DER-1).

Split out of schemas.py to keep that module under the 500-line modularity budget.
Re-exported via backend.models.schemas for backward compatibility.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class GoldRSSignal(str, Enum):
    AMPLIFIES_BULL = "AMPLIFIES_BULL"
    NEUTRAL = "NEUTRAL"
    FRAGILE = "FRAGILE"
    AMPLIFIES_BEAR = "AMPLIFIES_BEAR"


class GoldRS(BaseModel):
    signal: GoldRSSignal
    ratio_3m: Optional[Decimal] = None
    stock_return_3m: Optional[Decimal] = None
    gold_return_3m: Optional[Decimal] = None
    as_of: Optional[date] = None


class PiotroskiDetail(BaseModel):
    f1_net_profit_positive: bool = False
    f2_cfo_positive: bool = False
    f3_roe_improving: bool = False
    f4_quality_earnings: bool = False
    f5_leverage_falling: bool = False
    f6_liquidity_improving: bool = False
    f7_no_dilution: bool = False
    f8_margin_expanding: bool = False
    f9_asset_turnover_improving: bool = False


class Piotroski(BaseModel):
    score: int
    grade: str
    detail: PiotroskiDetail
    as_of: Optional[date] = None
