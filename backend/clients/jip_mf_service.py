"""JIP Mutual Fund Service — all MF-domain queries against de_mf_* tables."""

import asyncio
import time
from decimal import Decimal
from typing import Any, Optional, Sequence

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_mf_sql import (  # type: ignore[attr-defined]
    CATEGORIES_DECIMAL_FIELDS,
    CATEGORIES_SQL,
    CATEGORY_ALPHA_DECIMAL_FIELDS,
    CATEGORY_ALPHA_SQL,
    CATEGORY_NAV_RETURNS_DECIMAL_FIELDS,
    CATEGORY_NAV_RETURNS_SQL,
    FLOWS_DECIMAL_FIELDS,
    FLOWS_SQL,
    FRESHNESS_PROBE_KEYS,
    FRESHNESS_PROBE_SQL,
    FRESHNESS_TABLE_PROBES,
    FUND_DETAIL_DECIMAL_FIELDS,
    FUND_DETAIL_SQL,
    FUND_DETAIL_SQL_NO_WEIGHTED,
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
    RANK_FETCH_SQL,
    SECTORS_SQL,
    TOP_RS_SQL,
    UNIVERSE_DECIMAL_FIELDS,
    UNIVERSE_SQL,
    WEIGHTED_TECHNICALS_SQL,
)
from backend.clients.sql_fragments import safe_decimal

log = structlog.get_logger()

# Process-local TTL caches for the heavy MF aggregate queries. JIP data
# refreshes daily so a 5-minute cache is safe and prevents pool exhaustion
# from concurrent slow queries.
_MF_CACHE_TTL_SECONDS = 300
_mf_universe_cache: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}
_mf_universe_locks: dict[tuple[Any, ...], asyncio.Lock] = {}
_mf_categories_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_mf_categories_lock = asyncio.Lock()
_mf_rs_momentum_cache: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}
_mf_rs_momentum_lock = asyncio.Lock()
# Negative cache: when rs_momentum_batch fails (JIP-side timeout, missing
# index), record the failure timestamp so subsequent requests return empty
# immediately instead of burning 15s on every page load. Auto-retries
# after the TTL expires — when JIP ships ix_de_rs_scores_entity_type_id_date
# the next attempt will succeed and quadrants light back up. TTL is 1 hour
# because the underlying cause (missing JIP index) is not something that
# self-heals within a minute, and retrying every 60s meant every ~10th
# user request still burned 15s waiting for the same known-bad query.
_MF_RS_MOMENTUM_NEGATIVE_TTL_SECONDS = 3600
_mf_rs_momentum_last_failure: dict[str, float] = {}


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
        """Get the MF universe — is_etf=false is ALWAYS enforced. Cached 5m."""
        cache_key = (benchmark, category, broad_category, active_only)
        now = time.monotonic()
        cached = _mf_universe_cache.get(cache_key)
        if cached and now - cached[0] < _MF_CACHE_TTL_SECONDS:
            log.info("mf_universe_cache_hit", count=len(cached[1]))
            return cached[1]
        lock = _mf_universe_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = _mf_universe_cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < _MF_CACHE_TTL_SECONDS:
                log.info("mf_universe_cache_hit", count=len(cached[1]))
                return cached[1]
            rows = await self._fetch_mf_universe(
                benchmark=benchmark,
                category=category,
                broad_category=broad_category,
                active_only=active_only,
            )
            _mf_universe_cache[cache_key] = (time.monotonic(), rows)
            return rows

    async def _fetch_mf_universe(
        self,
        benchmark: Optional[str],
        category: Optional[str],
        broad_category: Optional[str],
        active_only: bool,
    ) -> list[dict[str, Any]]:
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
        """Get category-level aggregates with latest flows. Cached 5m."""
        now = time.monotonic()
        cached = _mf_categories_cache.get("default")
        if cached and now - cached[0] < _MF_CACHE_TTL_SECONDS:
            log.info("mf_categories_cache_hit", count=len(cached[1]))
            return cached[1]
        async with _mf_categories_lock:
            cached = _mf_categories_cache.get("default")
            if cached and time.monotonic() - cached[0] < _MF_CACHE_TTL_SECONDS:
                log.info("mf_categories_cache_hit", count=len(cached[1]))
                return cached[1]
            query_result = await self.session.execute(text(CATEGORIES_SQL))
            rows = [
                _decimalize(row, CATEGORIES_DECIMAL_FIELDS) for row in query_result.mappings().all()
            ]
            _mf_categories_cache["default"] = (time.monotonic(), rows)
            return rows

    async def get_mf_flows(self, months: int = 12) -> list[dict[str, Any]]:
        """Get category flows for the last N months."""
        query_result = await self.session.execute(text(FLOWS_SQL), {"months": months})
        return [_decimalize(row, FLOWS_DECIMAL_FIELDS) for row in query_result.mappings().all()]

    async def _has_weighted_technicals_table(self) -> bool:
        probe = await self.session.execute(
            text("SELECT to_regclass('public.de_mf_weighted_technicals') IS NOT NULL AS has_table")
        )
        row = probe.mappings().first()
        return bool(row["has_table"]) if row else False

    async def get_fund_detail(self, mstar_id: str) -> Optional[dict[str, Any]]:
        """Full deep-dive for a single fund.

        Falls back to a stripped query (NULL weighted technicals) when the
        de_mf_weighted_technicals source table is not yet provisioned in JIP.
        """
        sql = (
            FUND_DETAIL_SQL
            if await self._has_weighted_technicals_table()
            else FUND_DETAIL_SQL_NO_WEIGHTED
        )
        query_result = await self.session.execute(text(sql), {"mstar_id": mstar_id})
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
        """Get latest weighted technicals for a fund.

        Returns None if the JIP source table is not yet provisioned, so the
        deep-dive endpoint degrades gracefully instead of 500-ing.
        """
        if not await self._has_weighted_technicals_table():
            return None
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

        Uses a single batch CTE query (not N+1 per fund). Cached 5m.
        Negative-cached for 60s on failure: if the last attempt within the
        TTL raised (typically a statement_timeout from the missing JIP
        index), raise the same shape immediately so callers can fall back
        without burning another 15s per request.
        """
        now = time.monotonic()
        cached = _mf_rs_momentum_cache.get("default")
        if cached and now - cached[0] < _MF_CACHE_TTL_SECONDS:
            log.info("mf_rs_momentum_cache_hit", count=len(cached[1]))
            return cached[1]
        last_failure = _mf_rs_momentum_last_failure.get("default")
        if last_failure and now - last_failure < _MF_RS_MOMENTUM_NEGATIVE_TTL_SECONDS:
            log.info("mf_rs_momentum_negative_cache_hit")
            raise RuntimeError("rs_momentum_batch unavailable (negative-cached)")
        async with _mf_rs_momentum_lock:
            cached = _mf_rs_momentum_cache.get("default")
            if cached and time.monotonic() - cached[0] < _MF_CACHE_TTL_SECONDS:
                log.info("mf_rs_momentum_cache_hit", count=len(cached[1]))
                return cached[1]
            last_failure = _mf_rs_momentum_last_failure.get("default")
            if (
                last_failure
                and time.monotonic() - last_failure < _MF_RS_MOMENTUM_NEGATIVE_TTL_SECONDS
            ):
                log.info("mf_rs_momentum_negative_cache_hit")
                raise RuntimeError("rs_momentum_batch unavailable (negative-cached)")
            start_time = time.monotonic()
            try:
                query_result = await self.session.execute(text(RS_MOMENTUM_SQL))
                rows = [
                    _decimalize(row, RS_MOMENTUM_DECIMAL_FIELDS)
                    for row in query_result.mappings().all()
                ]
            except SQLAlchemyError:
                _mf_rs_momentum_last_failure["default"] = time.monotonic()
                log.warning(
                    "mf_rs_momentum_negative_cache_set",
                    ttl=_MF_RS_MOMENTUM_NEGATIVE_TTL_SECONDS,
                )
                raise
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            log.info("mf_rs_momentum_batch_fetched", count=len(rows), ms=elapsed_ms)
            momentum_map = {row["mstar_id"]: row for row in rows}
            _mf_rs_momentum_cache["default"] = (time.monotonic(), momentum_map)
            _mf_rs_momentum_last_failure.pop("default", None)  # clear negative cache on success
            return momentum_map

    async def get_category_nav_returns(self) -> list[dict[str, Any]]:
        """Get per-category 1Y average return computed from NAV history.

        Used by Brinson attribution as benchmark category returns.
        Returns rows with: category_name, fund_count, avg_return_1y, benchmark_weight.
        benchmark_weight = fund_count / total_active_funds (equal-weight benchmark).

        Returns empty list if de_mf_nav_daily has insufficient history.
        """
        try:
            query_result = await self.session.execute(text(CATEGORY_NAV_RETURNS_SQL))
            rows = [
                _decimalize(row, CATEGORY_NAV_RETURNS_DECIMAL_FIELDS)
                for row in query_result.mappings().all()
            ]
            log.info("category_nav_returns_fetched", count=len(rows))
            return rows
        except SQLAlchemyError as exc:
            log.warning("category_nav_returns_failed", error=str(exc))
            return []

    async def get_category_alpha(self) -> list[dict[str, Any]]:
        """Get per-category average manager_alpha.

        Used as selection effect proxy in Brinson attribution when
        per-fund raw returns are unavailable.
        Returns rows with: category_name, fund_count, avg_manager_alpha.
        """
        try:
            query_result = await self.session.execute(text(CATEGORY_ALPHA_SQL))
            rows = [
                _decimalize(row, CATEGORY_ALPHA_DECIMAL_FIELDS)
                for row in query_result.mappings().all()
            ]
            log.info("category_alpha_fetched", count=len(rows))
            return rows
        except SQLAlchemyError as exc:
            log.warning("category_alpha_failed", error=str(exc))
            return []

    async def get_fund_lifecycle(self, mstar_id: str) -> list[dict[str, Any]]:
        """Get lifecycle events for a fund."""
        query_result = await self.session.execute(text(LIFECYCLE_SQL), {"mstar_id": mstar_id})
        return [dict(row) for row in query_result.mappings().all()]

    async def get_mf_data_freshness(self) -> dict[str, Any]:
        """Get freshness dates for all MF tables.

        Tolerant of missing JIP tables: probes existence with to_regclass first,
        then queries MAX() only for tables that exist. A missing source table
        yields a NULL freshness value rather than 500-ing every MF endpoint.
        """
        probe_result = await self.session.execute(text(FRESHNESS_PROBE_SQL))
        probe_row = probe_result.mappings().first()
        if not probe_row:
            return {}

        out: dict[str, Any] = {key: None for key in FRESHNESS_PROBE_KEYS}
        out["active_fund_count"] = None

        select_parts: list[str] = []
        missing: list[str] = []
        for alias, table, column in FRESHNESS_TABLE_PROBES:
            if probe_row.get(FRESHNESS_PROBE_KEYS[alias]):
                select_parts.append(f"(SELECT MAX({column}) FROM {table}) AS {alias}")
            else:
                missing.append(table)

        if probe_row.get("has_master"):
            select_parts.append(
                "(SELECT COUNT(*) FROM de_mf_master "
                "WHERE is_active = true AND is_etf = false) AS active_fund_count"
            )

        if missing:
            log.warning("mf_freshness_missing_tables", missing=missing)

        if not select_parts:
            return out

        sql = "SELECT " + ", ".join(select_parts)
        freshness_rows = await self.session.execute(text(sql))
        row = freshness_rows.mappings().first()
        if row:
            out.update(dict(row))
        return out

    async def get_top_rs_funds(self) -> list[dict[str, Any]]:
        """All active non-ETF funds with their most-recent RS composite."""
        cursor = await self.session.execute(text(TOP_RS_SQL))
        return [dict(r) for r in cursor.mappings().all()]

    async def get_mf_rank_data(self) -> list[dict[str, Any]]:
        """Fetch rank scoring inputs: sharpe/vol/drawdown/IR for active funds."""
        cursor = await self.session.execute(text(RANK_FETCH_SQL))
        return [dict(r) for r in cursor.mappings().all()]
