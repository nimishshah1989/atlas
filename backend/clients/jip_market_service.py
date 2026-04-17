"""JIP Market Service — breadth, regime, and data freshness."""

from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


class JIPMarketService:
    """Read-only access to JIP market-level data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_market_breadth(self) -> Optional[dict[str, Any]]:
        """Get latest breadth data."""
        query = text("SELECT * FROM de_breadth_daily ORDER BY date DESC LIMIT 1")
        query_result = await self.session.execute(query)
        row = query_result.mappings().first()
        return dict(row) if row else None

    async def get_market_regime(self) -> Optional[dict[str, Any]]:
        """Get latest regime data."""
        query = text("SELECT * FROM de_market_regime ORDER BY date DESC LIMIT 1")
        query_result = await self.session.execute(query)
        row = query_result.mappings().first()
        return dict(row) if row else None

    async def get_data_freshness(self) -> dict[str, Any]:
        """Get latest dates for key data tables."""
        query = text("""
            SELECT
                (SELECT MAX(date) FROM de_equity_technical_daily) AS technicals_as_of,
                (SELECT MAX(date) FROM de_rs_scores
                 WHERE entity_type = 'equity') AS rs_scores_as_of,
                (SELECT MAX(date) FROM de_breadth_daily) AS breadth_as_of,
                (SELECT MAX(date) FROM de_market_regime) AS regime_as_of,
                (SELECT MAX(as_of_date) FROM de_mf_holdings) AS mf_holdings_as_of,
                (SELECT COUNT(*) FROM de_instrument WHERE is_active = true) AS active_stocks,
                (SELECT COUNT(DISTINCT sector) FROM de_instrument
                 WHERE is_active = true AND sector IS NOT NULL) AS sectors
        """)
        query_result = await self.session.execute(query)
        row = query_result.mappings().first()
        return dict(row) if row else {}

    async def get_latest_rs_date(self) -> Optional[str]:
        """Return MAX(date) from de_rs_scores as an ISO date string.

        Punch list item 3: replaces the direct de_* SQL in pipeline.py.
        Returns None if the table is empty or the query fails.
        """
        try:
            query = text("SELECT MAX(date) FROM de_rs_scores")
            query_result = await self.session.execute(query)
            latest_date = query_result.scalar_one_or_none()
            if latest_date is None:
                return None
            return str(latest_date)
        except Exception as exc:
            log.warning("latest_rs_date_query_failed", error=str(exc))
            return None

    async def get_macro_ratios(
        self, tickers: Optional[list[str]] = None, sparkline_n: int = 10
    ) -> list[dict[str, Any]]:
        """Return macro series with latest value and last N sparkline points.

        Queries de_macro_values joined with de_macro_master for name/unit.
        Returns one dict per ticker with ``sparkline`` list ordered ascending.
        """
        default_tickers = [
            "DGS10",
            "VIXCLS",
            "INDIAVIX",
            "DXY",
            "BRENT",
            "GOLD",
            "SP500",
            "USDINR",
        ]
        target = tickers or default_tickers
        # Use ANY(:tickers) to pass list; asyncpg expects a Python list.
        query = text("""
            WITH ranked AS (
                SELECT
                    mv.ticker,
                    mv.date,
                    mv.value,
                    ROW_NUMBER() OVER (PARTITION BY mv.ticker ORDER BY mv.date DESC) AS rn
                FROM de_macro_values mv
                WHERE mv.ticker = ANY(:tickers)
            ),
            latest AS (
                SELECT ticker, value AS latest_value, date AS latest_date
                FROM ranked
                WHERE rn = 1
            ),
            spark AS (
                SELECT ticker, date, value
                FROM ranked
                WHERE rn <= :sparkline_n
            )
            SELECT
                l.ticker,
                mm.name,
                mm.unit,
                l.latest_value,
                l.latest_date,
                COALESCE(
                    JSON_AGG(
                        JSON_BUILD_OBJECT('date', s.date, 'value', s.value)
                        ORDER BY s.date ASC
                    ) FILTER (WHERE s.date IS NOT NULL),
                    '[]'::json
                ) AS sparkline
            FROM latest l
            LEFT JOIN de_macro_master mm ON mm.ticker = l.ticker
            LEFT JOIN spark s ON s.ticker = l.ticker
            GROUP BY l.ticker, mm.name, mm.unit, l.latest_value, l.latest_date
            ORDER BY l.ticker
        """)
        try:
            query_result = await self.session.execute(
                query,
                {"tickers": target, "sparkline_n": sparkline_n},
            )
            rows = query_result.mappings().all()
            out = []
            for row in rows:
                sparkline_raw = row["sparkline"] or []
                # sparkline comes as list[dict] from JSON_AGG
                if isinstance(sparkline_raw, str):
                    import json

                    sparkline_raw = json.loads(sparkline_raw)
                out.append(
                    {
                        "ticker": row["ticker"],
                        "name": row["name"],
                        "unit": row["unit"],
                        "latest_value": row["latest_value"],
                        "latest_date": row["latest_date"],
                        "sparkline": sparkline_raw,
                    }
                )
            log.info("macro_ratios_fetched", count=len(out))
            return out
        except Exception as exc:
            log.warning("get_macro_ratios_failed", error=str(exc)[:300])
            return []

    async def get_macro_ratios_v7(
        self, tickers: Optional[list[str]] = None, sparkline_n: int = 10
    ) -> list[dict[str, Any]]:
        """Return 9 macro series with sparkline + MoM change.

        Same as get_macro_ratios but adds mom_change field and defaults to 9 tickers.
        MoM change = latest_value - value at ~30 trading days ago (rn=31).
        If rn=31 doesn't exist (short series), mom_change = None.
        """
        _v7_default_tickers = [
            "DGS10",
            "VIXCLS",
            "INDIAVIX",
            "DXY",
            "BRENT",
            "GOLD",
            "SP500",
            "USDINR",
            "FEDFUNDS",
        ]
        target = tickers or _v7_default_tickers
        query = text("""
            WITH ranked AS (
                SELECT
                    mv.ticker,
                    mv.date,
                    mv.value,
                    ROW_NUMBER() OVER (PARTITION BY mv.ticker ORDER BY mv.date DESC) AS rn
                FROM de_macro_values mv
                WHERE mv.ticker = ANY(:tickers)
            ),
            latest AS (
                SELECT ticker, value AS latest_value, date AS latest_date
                FROM ranked WHERE rn = 1
            ),
            month_ago AS (
                SELECT ticker, value AS month_ago_value
                FROM ranked WHERE rn = 31
            ),
            spark AS (
                SELECT ticker, date, value
                FROM ranked WHERE rn <= :sparkline_n
            )
            SELECT
                l.ticker,
                mm.name,
                mm.unit,
                l.latest_value,
                l.latest_date,
                ma.month_ago_value,
                COALESCE(
                    JSON_AGG(
                        JSON_BUILD_OBJECT('date', s.date, 'value', s.value)
                        ORDER BY s.date ASC
                    ) FILTER (WHERE s.date IS NOT NULL),
                    '[]'::json
                ) AS sparkline
            FROM latest l
            LEFT JOIN de_macro_master mm ON mm.ticker = l.ticker
            LEFT JOIN spark s ON s.ticker = l.ticker
            LEFT JOIN month_ago ma ON ma.ticker = l.ticker
            GROUP BY l.ticker, mm.name, mm.unit, l.latest_value, l.latest_date, ma.month_ago_value
            ORDER BY l.ticker
        """)
        try:
            query_result = await self.session.execute(
                query, {"tickers": target, "sparkline_n": sparkline_n}
            )
            rows = query_result.mappings().all()
            out = []
            for row in rows:
                sparkline_raw = row["sparkline"] or []
                if isinstance(sparkline_raw, str):
                    import json

                    sparkline_raw = json.loads(sparkline_raw)
                latest_val = row["latest_value"]
                month_ago_val = row["month_ago_value"]
                mom_change = None
                if latest_val is not None and month_ago_val is not None:
                    from decimal import Decimal as _Decimal

                    mom_change = _Decimal(str(latest_val)) - _Decimal(str(month_ago_val))
                out.append(
                    {
                        "ticker": row["ticker"],
                        "name": row["name"],
                        "unit": row["unit"],
                        "latest_value": latest_val,
                        "latest_date": row["latest_date"],
                        "mom_change": mom_change,
                        "sparkline": sparkline_raw,
                    }
                )
            log.info("macro_ratios_v7_fetched", count=len(out))
            return out
        except Exception as exc:
            log.warning("get_macro_ratios_v7_failed", error=str(exc)[:300])
            return []

    async def get_global_rs_heatmap_all(self) -> list[dict[str, Any]]:
        """Return all 131 global instruments with latest RS and price.

        Unlike get_global_rs_heatmap(), starts from de_global_instrument_master
        so instruments without RS scores are still included (total=131).
        """
        query = text("""
            WITH latest_rs AS (
                SELECT DISTINCT ON (entity_id)
                    entity_id,
                    date AS rs_date,
                    rs_composite,
                    rs_1m,
                    rs_3m
                FROM de_rs_scores
                WHERE entity_type = 'global'
                ORDER BY entity_id, date DESC
            ),
            latest_price AS (
                SELECT DISTINCT ON (ticker)
                    ticker,
                    date AS price_date,
                    close
                FROM de_global_prices
                ORDER BY ticker, date DESC
            )
            SELECT
                gim.ticker AS entity_id,
                gim.name,
                gim.instrument_type,
                gim.country,
                lr.rs_composite,
                lr.rs_1m,
                lr.rs_3m,
                lr.rs_date,
                lp.close,
                lp.price_date
            FROM de_global_instrument_master gim
            LEFT JOIN latest_rs lr ON lr.entity_id = gim.ticker
            LEFT JOIN latest_price lp ON lp.ticker = gim.ticker
            ORDER BY gim.instrument_type ASC NULLS LAST, lr.rs_composite DESC NULLS LAST
        """)
        try:
            query_result = await self.session.execute(query)
            rows = query_result.mappings().all()
            out = [dict(row) for row in rows]
            log.info("global_rs_heatmap_all_fetched", count=len(out))
            return out
        except Exception as exc:
            log.warning("get_global_rs_heatmap_all_failed", error=str(exc)[:300])
            return []

    async def get_global_indices(self) -> list[dict[str, Any]]:
        """Return global indices with latest RS scores and gold_rs_signal.

        Filters de_global_instrument_master to instrument_type='indices'.
        Joins atlas_gold_rs_cache for gold_rs_signal.
        """
        query = text("""
            WITH latest_rs AS (
                SELECT DISTINCT ON (entity_id)
                    entity_id,
                    date AS rs_date,
                    rs_composite,
                    rs_1m,
                    rs_3m
                FROM de_rs_scores
                WHERE entity_type = 'global'
                ORDER BY entity_id, date DESC
            ),
            latest_price AS (
                SELECT DISTINCT ON (ticker)
                    ticker,
                    date AS price_date,
                    close
                FROM de_global_prices
                ORDER BY ticker, date DESC
            ),
            latest_gold_rs AS (
                SELECT DISTINCT ON (entity_id)
                    entity_id,
                    gold_rs_signal
                FROM atlas_gold_rs_cache
                WHERE entity_type = 'global'
                ORDER BY entity_id, date DESC
            )
            SELECT
                gim.ticker AS entity_id,
                gim.name,
                gim.country,
                lr.rs_composite,
                lr.rs_1m,
                lr.rs_3m,
                lr.rs_date,
                lp.close,
                lp.price_date,
                gr.gold_rs_signal
            FROM de_global_instrument_master gim
            LEFT JOIN latest_rs lr ON lr.entity_id = gim.ticker
            LEFT JOIN latest_price lp ON lp.ticker = gim.ticker
            LEFT JOIN latest_gold_rs gr ON gr.entity_id = gim.ticker
            WHERE gim.instrument_type = 'indices'
            ORDER BY lr.rs_composite DESC NULLS LAST
        """)
        try:
            query_result = await self.session.execute(query)
            rows = query_result.mappings().all()
            out = [dict(row) for row in rows]
            log.info("global_indices_fetched", count=len(out))
            return out
        except Exception as exc:
            log.warning("get_global_indices_failed", error=str(exc)[:300])
            return []

    async def get_global_rs_heatmap(self) -> list[dict[str, Any]]:
        """Return global instrument RS scores with latest price.

        Joins de_rs_scores (entity_type='global') with de_global_prices and
        de_global_instrument_master. Uses DISTINCT ON to get latest RS date
        per entity and latest price per ticker.
        """
        query = text("""
            WITH latest_rs AS (
                SELECT DISTINCT ON (entity_id)
                    entity_id,
                    date AS rs_date,
                    rs_composite,
                    rs_1m,
                    rs_3m
                FROM de_rs_scores
                WHERE entity_type = 'global'
                ORDER BY entity_id, date DESC
            ),
            latest_price AS (
                SELECT DISTINCT ON (ticker)
                    ticker,
                    date AS price_date,
                    close
                FROM de_global_prices
                ORDER BY ticker, date DESC
            )
            SELECT
                lr.entity_id,
                COALESCE(gim.name, lr.entity_id) AS name,
                gim.instrument_type,
                gim.country,
                lr.rs_composite,
                lr.rs_1m,
                lr.rs_3m,
                lr.rs_date,
                lp.close,
                lp.price_date
            FROM latest_rs lr
            LEFT JOIN de_global_instrument_master gim ON gim.ticker = lr.entity_id
            LEFT JOIN latest_price lp ON lp.ticker = lr.entity_id
            ORDER BY lr.rs_composite DESC NULLS LAST
        """)
        try:
            query_result = await self.session.execute(query)
            rows = query_result.mappings().all()
            out = [dict(row) for row in rows]
            log.info("global_rs_heatmap_fetched", count=len(out))
            return out
        except Exception as exc:
            log.warning("get_global_rs_heatmap_failed", error=str(exc)[:300])
            return []
