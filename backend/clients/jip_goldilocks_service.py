"""JIP Goldilocks Service — read de_goldilocks_* tables (read-only, never write).

Provides Goldilocks stock ideas, market view, and sector view from the JIP data layer.
All methods return empty lists gracefully if the tables do not exist.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


class JIPGoldilocksService:
    """Read-only access to JIP Goldilocks data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_goldilocks_stock_ideas(
        self,
        date_from: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Get Goldilocks stock recommendations.

        Returns rows from de_goldilocks_stock_ideas with symbol, action,
        entry_price, target_price, stop_loss, rationale, and idea_date.

        If the table does not exist (dev environment), returns [].
        If date_from is None, returns the latest batch (most recent idea_date).
        """
        try:
            if date_from is not None:
                query = text("""
                    SELECT
                        symbol,
                        action,
                        entry_price,
                        target_price,
                        stop_loss,
                        rationale,
                        idea_date,
                        sector,
                        confidence
                    FROM de_goldilocks_stock_ideas
                    WHERE idea_date >= :date_from
                    ORDER BY idea_date DESC, symbol
                    LIMIT :limit
                """)
                params: dict[str, Any] = {"date_from": date_from, "limit": limit}
            else:
                # Fetch latest date's ideas
                query = text("""
                    WITH latest_date AS (
                        SELECT MAX(idea_date) AS max_date
                        FROM de_goldilocks_stock_ideas
                    )
                    SELECT
                        g.symbol,
                        g.action,
                        g.entry_price,
                        g.target_price,
                        g.stop_loss,
                        g.rationale,
                        g.idea_date,
                        g.sector,
                        g.confidence
                    FROM de_goldilocks_stock_ideas g
                    JOIN latest_date ld ON g.idea_date = ld.max_date
                    ORDER BY g.symbol
                    LIMIT :limit
                """)
                params = {"limit": limit}

            query_out = await self.session.execute(query, params)
            rows = [dict(row) for row in query_out.mappings().all()]
            log.info("goldilocks_stock_ideas_fetched", count=len(rows))
            return rows

        except ProgrammingError as exc:
            if "de_goldilocks_stock_ideas" in str(exc):
                log.warning("goldilocks_stock_ideas_table_missing")
                return []
            raise

    async def get_goldilocks_market_view(self) -> Optional[dict[str, Any]]:
        """Get the latest Goldilocks market view.

        Returns None if table is missing or no data.
        """
        try:
            query = text("""
                SELECT
                    view_date,
                    market_stance,
                    market_rationale,
                    key_risks,
                    index_target
                FROM de_goldilocks_market_view
                ORDER BY view_date DESC
                LIMIT 1
            """)
            query_out = await self.session.execute(query)
            row = query_out.mappings().first()
            return dict(row) if row else None

        except ProgrammingError as exc:
            if "de_goldilocks_market_view" in str(exc):
                log.warning("goldilocks_market_view_table_missing")
                return None
            raise

    async def get_goldilocks_sector_view(self) -> list[dict[str, Any]]:
        """Get the latest Goldilocks sector rankings.

        Returns [] if table is missing or no data.
        """
        try:
            query = text("""
                WITH latest_date AS (
                    SELECT MAX(view_date) AS max_date
                    FROM de_goldilocks_sector_view
                )
                SELECT
                    s.sector,
                    s.ranking,
                    s.stance,
                    s.rationale,
                    s.view_date
                FROM de_goldilocks_sector_view s
                JOIN latest_date ld ON s.view_date = ld.max_date
                ORDER BY s.ranking
            """)
            query_out = await self.session.execute(query)
            rows = [dict(row) for row in query_out.mappings().all()]
            log.info("goldilocks_sector_view_fetched", count=len(rows))
            return rows

        except ProgrammingError as exc:
            if "de_goldilocks_sector_view" in str(exc):
                log.warning("goldilocks_sector_view_table_missing")
                return []
            raise
