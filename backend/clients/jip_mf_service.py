"""JIP Mutual Fund Service — MF holder queries."""

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


class JIPMFService:
    """Read-only access to JIP mutual fund data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_mf_holders(self, symbol: str) -> list[dict[str, Any]]:
        """Get mutual funds holding a specific stock."""
        query = text("""
            SELECT h.mstar_id, m.scheme_name, h.weight_pct, h.shares_held, h.market_value
            FROM de_mf_holdings h
            JOIN de_instrument i ON h.instrument_id = i.id
            JOIN de_mf_master m ON h.mstar_id = m.mstar_id
            WHERE i.current_symbol = :symbol
              AND h.as_of_date = (SELECT MAX(as_of_date) FROM de_mf_holdings)
            ORDER BY h.weight_pct DESC NULLS LAST
            LIMIT 50
        """)
        query_result = await self.session.execute(query, {"symbol": symbol.upper()})
        return [dict(row) for row in query_result.mappings().all()]
