"""JIP Mutual Fund Service — all MF-domain queries against de_mf_* tables."""

import time
from decimal import Decimal
from typing import Any, Optional, Sequence

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_mf_sql import (
    CATEGORIES_DECIMAL_FIELDS,
    CATEGORIES_SQL,
    FLOWS_DECIMAL_FIELDS,
    FLOWS_SQL,
    FRESHNESS_SQL,
    FUND_DETAIL_DECIMAL_FIELDS,
    FUND_DETAIL_SQL,
    HOLDERS_SQL,
    HOLDINGS_SQL,
    LIFECYCLE_SQL,
    NAV_HISTORY_SQL_TEMPLATE,
    OVERLAP_AGG_SQL,
    OVERLAP_DETAIL_SQL,
    RS_HISTORY_DECIMAL_FIELDS,
    RS_HISTORY_SQL,
    RS_MOMENTUM_DECIMAL_FIELDS,
    RS_MOMENTUM_SQL,
    SECTORS_SQL,
    UNIVERSE_DECIMAL_FIELDS,
    UNIVERSE_SQL,
    WEIGHTED_TECHNICALS_SQL,
)
from backend.clients.sql_fragments import safe_decimal

log = structlog.get_logger()


def _decimalize(
    mapping: Any,
    fields: Sequence[str],
) -> dict[str, Any]:
    """Convert a row mapping to dict, applying safe_decimal to named fields."""
    record = dict(mapping)
    for field_name in fields:
        record[field_name] = safe_decimal(record.get(field_name))
    return record


class JIPMFService:
    """Read-only access to JIP mutual fund data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_mf_holders(self, symbol: str) -> list[dict[str, Any]]:
        """Get mutual funds holding a specific stock."""
        cursor = await self.session.execute(text(HOLDERS_SQL), {"symbol": symbol.upper()})
        return [_decimalize(row, ("weight_pct", "market_value")) for row in cursor.mappings().all()]

    async def get_mf_universe(
        self,
        benchmark: Optional[str] = None,
        category: Optional[str] = None,
        broad_category: Optional[str] = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Get the MF universe — is_etf=false is ALWAYS enforced."""
        start_time = time.monotonic()

        conditions = ["m.is_etf = false"]
        params: dict[str, Any] = {}

        if active_only:
            conditions.append("m.is_active = true")
        if category:
            conditions.append("m.category_name = :category")
            params["category"] = category
        if broad_category:
            conditions.append("m.broad_category = :broad_category")
            params["broad_category"] = broad_category

        where_clause = " AND ".join(conditions)
        query = text(UNIVERSE_SQL.format(where_clause=where_clause))
        query_result = await self.session.execute(query, params)
        rows = [_decimalize(row, UNIVERSE_DECIMAL_FIELDS) for row in query_result.mappings().all()]

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        log.info("mf_universe_fetched", count=len(rows), ms=elapsed_ms)
        return rows

    async def get_mf_categories(self) -> list[dict[str, Any]]:
        """Get category-level aggregates with latest flows."""
        query_result = await self.session.execute(text(CATEGORIES_SQL))
        return [
            _decimalize(row, CATEGORIES_DECIMAL_FIELDS) for row in query_result.mappings().all()
        ]

    async def get_mf_flows(self, months: int = 12) -> list[dict[str, Any]]:
        """Get category flows for the last N months."""
        query_result = await self.session.execute(text(FLOWS_SQL), {"months": months})
        return [_decimalize(row, FLOWS_DECIMAL_FIELDS) for row in query_result.mappings().all()]

    async def get_fund_detail(self, mstar_id: str) -> Optional[dict[str, Any]]:
        """Full deep-dive for a single fund."""
        query_result = await self.session.execute(text(FUND_DETAIL_SQL), {"mstar_id": mstar_id})
        row = query_result.mappings().first()
        if not row:
            return None
        return _decimalize(row, FUND_DETAIL_DECIMAL_FIELDS)

    async def get_fund_holdings(self, mstar_id: str) -> list[dict[str, Any]]:
        """Get latest holdings for a fund with stock RS and technicals."""
        query_result = await self.session.execute(text(HOLDINGS_SQL), {"mstar_id": mstar_id})
        return [
            _decimalize(row, ("weight_pct", "market_value", "rs_composite", "rsi_14"))
            for row in query_result.mappings().all()
        ]

    async def get_fund_sectors(self, mstar_id: str) -> list[dict[str, Any]]:
        """Get sector exposure for a fund at latest as_of_date."""
        query_result = await self.session.execute(text(SECTORS_SQL), {"mstar_id": mstar_id})
        return [_decimalize(row, ("weight_pct",)) for row in query_result.mappings().all()]

    async def get_fund_rs_history(
        self,
        mstar_id: str,
        months: int = 12,
    ) -> list[dict[str, Any]]:
        """Get RS score history for a fund."""
        query_result = await self.session.execute(
            text(RS_HISTORY_SQL), {"mstar_id": mstar_id, "months": months}
        )
        return [
            _decimalize(row, RS_HISTORY_DECIMAL_FIELDS) for row in query_result.mappings().all()
        ]

    async def get_fund_weighted_technicals(self, mstar_id: str) -> Optional[dict[str, Any]]:
        """Get latest weighted technicals for a fund."""
        query_result = await self.session.execute(
            text(WEIGHTED_TECHNICALS_SQL), {"mstar_id": mstar_id}
        )
        row = query_result.mappings().first()
        if not row:
            return None
        return _decimalize(
            row,
            ("weighted_rsi", "weighted_breadth_pct_above_200dma", "weighted_macd_bullish_pct"),
        )

    async def get_fund_nav_history(
        self,
        mstar_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get NAV history for a fund with optional date range."""
        conditions = ["mstar_id = :mstar_id"]
        params: dict[str, Any] = {"mstar_id": mstar_id}

        if date_from:
            conditions.append("nav_date >= :date_from")
            params["date_from"] = date_from
        if date_to:
            conditions.append("nav_date <= :date_to")
            params["date_to"] = date_to

        where_clause = " AND ".join(conditions)
        query = text(NAV_HISTORY_SQL_TEMPLATE.format(where_clause=where_clause))
        query_result = await self.session.execute(query, params)
        return [_decimalize(row, ("nav",)) for row in query_result.mappings().all()]

    async def get_fund_overlap(self, mstar_id_a: str, mstar_id_b: str) -> dict[str, Any]:
        """Compute portfolio overlap between two funds."""
        overlap_params = {"mstar_id_a": mstar_id_a, "mstar_id_b": mstar_id_b}

        agg_result = await self.session.execute(text(OVERLAP_AGG_SQL), overlap_params)
        agg_row = agg_result.mappings().first()

        detail_result = await self.session.execute(text(OVERLAP_DETAIL_SQL), overlap_params)
        common_holdings = [
            _decimalize(row, ("weight_pct_a", "weight_pct_b"))
            for row in detail_result.mappings().all()
        ]

        overlap_pct = (
            safe_decimal(agg_row.get("overlap_pct")) or Decimal("0") if agg_row else Decimal("0")
        )

        return {
            "mstar_id_a": mstar_id_a,
            "mstar_id_b": mstar_id_b,
            "overlap_pct": overlap_pct,
            "common_count": agg_row.get("common_count", 0) if agg_row else 0,
            "count_a": agg_row.get("count_a", 0) if agg_row else 0,
            "count_b": agg_row.get("count_b", 0) if agg_row else 0,
            "common_holdings": common_holdings,
        }

    async def get_mf_rs_momentum_batch(self) -> dict[str, dict[str, Any]]:
        """Batch-fetch latest + 28-day-ago RS composite for all MF entities.

        Returns a dict keyed by mstar_id, each value containing:
            - mstar_id: str
            - latest_date: date | None
            - latest_rs_composite: Decimal | None
            - past_date: date | None
            - past_rs_composite: Decimal | None
            - rs_momentum_28d: Decimal | None  (None if <28 days of history)

        Uses a single batch CTE query (not N+1 per fund). Efficient for 800+ funds.
        """
        start_time = time.monotonic()
        query_result = await self.session.execute(text(RS_MOMENTUM_SQL))
        rows = [
            _decimalize(row, RS_MOMENTUM_DECIMAL_FIELDS) for row in query_result.mappings().all()
        ]
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        log.info("mf_rs_momentum_batch_fetched", count=len(rows), ms=elapsed_ms)
        return {row["mstar_id"]: row for row in rows}

    async def get_fund_lifecycle(self, mstar_id: str) -> list[dict[str, Any]]:
        """Get lifecycle events for a fund."""
        query_result = await self.session.execute(text(LIFECYCLE_SQL), {"mstar_id": mstar_id})
        return [dict(row) for row in query_result.mappings().all()]

    async def get_mf_data_freshness(self) -> dict[str, Any]:
        """Get freshness dates for all MF tables."""
        query_result = await self.session.execute(text(FRESHNESS_SQL))
        row = query_result.mappings().first()
        return dict(row) if row else {}
