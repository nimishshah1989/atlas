"""Pydantic v2 models for insider trades, bulk deals, and block deals routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, model_serializer


# ---------------------------------------------------------------------------
# Insider trades
# ---------------------------------------------------------------------------


class InsiderTradePoint(BaseModel):
    txn_date: date
    filing_date: Optional[date] = None
    person_name: Optional[str] = None
    person_category: Optional[str] = None
    txn_type: Optional[str] = None
    qty: Optional[int] = None
    value_inr: Optional[Decimal] = None
    post_holding_pct: Optional[Decimal] = None


class InsiderMeta(BaseModel):
    symbol: str
    from_date: date
    to_date: date
    data_as_of: Optional[date] = None
    point_count: int
    limit: int


class InsiderResponse(BaseModel):
    insider_trades: list[InsiderTradePoint]
    meta: InsiderMeta

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "data": [p.model_dump(mode="json") for p in self.insider_trades],
            "_meta": self.meta.model_dump(mode="json"),
        }


# ---------------------------------------------------------------------------
# Bulk deals
# ---------------------------------------------------------------------------


class BulkDealPoint(BaseModel):
    trade_date: date
    client_name: Optional[str] = None
    txn_type: Optional[str] = None
    qty: Optional[int] = None
    avg_price: Optional[Decimal] = None


class BulkDealMeta(BaseModel):
    symbol: str
    from_date: date
    to_date: date
    data_as_of: Optional[date] = None
    point_count: int


class BulkDealResponse(BaseModel):
    bulk_deals: list[BulkDealPoint]
    meta: BulkDealMeta

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "data": [p.model_dump(mode="json") for p in self.bulk_deals],
            "_meta": self.meta.model_dump(mode="json"),
        }


# ---------------------------------------------------------------------------
# Block deals
# ---------------------------------------------------------------------------


class BlockDealPoint(BaseModel):
    trade_date: date
    client_name: Optional[str] = None
    txn_type: Optional[str] = None
    qty: Optional[int] = None
    trade_price: Optional[Decimal] = None


class BlockDealMeta(BaseModel):
    symbol: str
    from_date: date
    to_date: date
    data_as_of: Optional[date] = None
    point_count: int


class BlockDealResponse(BaseModel):
    block_deals: list[BlockDealPoint]
    meta: BlockDealMeta

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "data": [p.model_dump(mode="json") for p in self.block_deals],
            "_meta": self.meta.model_dump(mode="json"),
        }
