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
                (SELECT MAX(date) FROM de_rs_scores WHERE entity_type = 'equity') AS rs_scores_as_of,
                (SELECT MAX(date) FROM de_breadth_daily) AS breadth_as_of,
                (SELECT MAX(date) FROM de_market_regime) AS regime_as_of,
                (SELECT MAX(as_of_date) FROM de_mf_holdings) AS mf_holdings_as_of,
                (SELECT COUNT(*) FROM de_instrument WHERE is_active = true) AS active_stocks,
                (SELECT COUNT(DISTINCT sector) FROM de_instrument WHERE is_active = true AND sector IS NOT NULL) AS sectors
        """)
        query_result = await self.session.execute(query)
        row = query_result.mappings().first()
        return dict(row) if row else {}
