"""JIP Data Service — facade delegating to specialized service modules.

When the JIP /internal/ API comes online, swap the underlying services
with httpx clients. The facade interface (return types) stays identical.
"""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_equity_service import JIPEquityService
from backend.clients.jip_market_service import JIPMarketService
from backend.clients.jip_mf_service import JIPMFService
from backend.clients.jip_query_service import JIPQueryService
from backend.clients.sql_fragments import safe_decimal as _dec  # noqa: F401


class JIPDataService:
    """Read-only access to JIP de_* tables — delegates to specialized services."""

    def __init__(self, session: AsyncSession):
        self._equity = JIPEquityService(session)
        self._market = JIPMarketService(session)
        self._mf = JIPMFService(session)
        self._query = JIPQueryService(session)

    async def get_equity_universe(
        self,
        benchmark: Optional[str] = "NIFTY 500",
        sector: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return await self._equity.get_equity_universe(benchmark=benchmark, sector=sector)

    async def get_sector_rollups(self) -> list[dict[str, Any]]:
        return await self._equity.get_sector_rollups()

    async def get_stock_detail(self, symbol: str) -> Optional[dict[str, Any]]:
        return await self._equity.get_stock_detail(symbol)

    async def get_market_breadth(self) -> Optional[dict[str, Any]]:
        return await self._market.get_market_breadth()

    async def get_market_regime(self) -> Optional[dict[str, Any]]:
        return await self._market.get_market_regime()

    async def get_rs_history(
        self,
        symbol: str,
        benchmark: str = "NIFTY 500",
        months: int = 12,
    ) -> list[dict[str, Any]]:
        return await self._equity.get_rs_history(symbol, benchmark=benchmark, months=months)

    async def get_movers(self, limit: int = 15) -> dict[str, list[dict[str, Any]]]:
        return await self._equity.get_movers(limit=limit)

    async def get_data_freshness(self) -> dict[str, Any]:
        return await self._market.get_data_freshness()

    async def get_mf_holders(self, symbol: str) -> list[dict[str, Any]]:
        return await self._mf.get_mf_holders(symbol)

    async def query_equity(
        self,
        filters: list[dict[str, Any]],
        sort: list[dict[str, Any]],
        limit: int = 50,
        offset: int = 0,
        fields: Optional[list[str]] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        return await self._query.query_equity(
            filters=filters,
            sort_specs=sort,
            limit=limit,
            offset=offset,
            fields=fields,
        )
