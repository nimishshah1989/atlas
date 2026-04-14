"""JIP Data Service — facade delegating to specialized service modules.

When the JIP /internal/ API comes online, swap the underlying services
with httpx clients. The facade interface (return types) stays identical.
"""

from typing import Any, Optional

import asyncpg.exceptions
import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.clients.jip_equity_service import JIPEquityService
from backend.clients.jip_market_service import JIPMarketService
from backend.clients.jip_mf_service import JIPMFService
from backend.clients.jip_query_service import JIPQueryService
from backend.clients.sql_fragments import safe_decimal as _dec  # noqa: F401
from backend.db.session import async_session_factory
from backend.services.uql import errors as uql_errors
from backend.services.uql.optimizer import SQLPlan

# §17.9 hard ceiling: every UQL query runs inside a transaction that
# `SET LOCAL statement_timeout = 2000` shortens to two seconds. Past that
# PostgreSQL cancels the statement and asyncpg raises QueryCanceledError,
# which the executor translates into a 504 QUERY_TIMEOUT.
STATEMENT_TIMEOUT_MS = 2000

log = structlog.get_logger()


def _is_query_canceled(exc: BaseException) -> bool:
    """Walk the exception chain looking for asyncpg's QueryCanceledError.

    SQLAlchemy wraps the asyncpg cause in ``DBAPIError.orig`` but the
    cause chain (``__cause__``/``__context__``) sometimes carries it one
    level deeper, so we walk both.
    """

    stack: list[BaseException] = [exc]
    seen: set[int] = set()
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        if isinstance(cur, asyncpg.exceptions.QueryCanceledError):
            return True
        orig = getattr(cur, "orig", None)
        if isinstance(orig, BaseException):
            stack.append(orig)
        if cur.__cause__ is not None:
            stack.append(cur.__cause__)
        if cur.__context__ is not None:
            stack.append(cur.__context__)
    return False


class JIPDataService:
    """Read-only access to JIP de_* tables — delegates to specialized services."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ):
        self._equity = JIPEquityService(session)
        self._market = JIPMarketService(session)
        self._mf = JIPMFService(session)
        self._query = JIPQueryService(session)
        self._session_factory = session_factory or async_session_factory

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

    async def get_mf_universe(
        self,
        benchmark: Optional[str] = None,
        category: Optional[str] = None,
        broad_category: Optional[str] = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        return await self._mf.get_mf_universe(
            benchmark=benchmark,
            category=category,
            broad_category=broad_category,
            active_only=active_only,
        )

    async def get_mf_categories(self) -> list[dict[str, Any]]:
        return await self._mf.get_mf_categories()

    async def get_mf_flows(self, months: int = 12) -> list[dict[str, Any]]:
        return await self._mf.get_mf_flows(months=months)

    async def get_fund_detail(self, mstar_id: str) -> Optional[dict[str, Any]]:
        return await self._mf.get_fund_detail(mstar_id)

    async def get_fund_holdings(self, mstar_id: str) -> list[dict[str, Any]]:
        return await self._mf.get_fund_holdings(mstar_id)

    async def get_fund_sectors(self, mstar_id: str) -> list[dict[str, Any]]:
        return await self._mf.get_fund_sectors(mstar_id)

    async def get_fund_rs_history(
        self,
        mstar_id: str,
        months: int = 12,
    ) -> list[dict[str, Any]]:
        return await self._mf.get_fund_rs_history(mstar_id, months=months)

    async def get_fund_weighted_technicals(self, mstar_id: str) -> Optional[dict[str, Any]]:
        return await self._mf.get_fund_weighted_technicals(mstar_id)

    async def get_fund_nav_history(
        self,
        mstar_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return await self._mf.get_fund_nav_history(mstar_id, date_from=date_from, date_to=date_to)

    async def get_fund_overlap(self, mstar_id_a: str, mstar_id_b: str) -> dict[str, Any]:
        return await self._mf.get_fund_overlap(mstar_id_a, mstar_id_b)

    async def get_fund_lifecycle(self, mstar_id: str) -> list[dict[str, Any]]:
        return await self._mf.get_fund_lifecycle(mstar_id)

    async def get_mf_data_freshness(self) -> dict[str, Any]:
        return await self._mf.get_mf_data_freshness()

    async def get_mf_rs_momentum_batch(self) -> dict[str, dict[str, Any]]:
        return await self._mf.get_mf_rs_momentum_batch()

    async def get_latest_rs_date(self) -> Optional[str]:
        return await self._market.get_latest_rs_date()

    async def execute_sql_plan(self, plan: SQLPlan) -> tuple[list[dict[str, Any]], int]:
        """Execute a compiled :class:`SQLPlan` under a 2-second timeout.

        Opens a fresh ``AsyncSession`` from the connection pool, begins a
        transaction, and issues ``SET LOCAL statement_timeout = 2000`` so
        the cap dies with the transaction even if the same connection is
        re-checked-out later. Optional ``count_sql`` runs first; the data
        query runs second; both share the timeout window. On
        ``asyncpg.exceptions.QueryCanceledError`` we raise a
        ``QUERY_TIMEOUT`` :class:`UQLError` (HTTP 504); other DB errors
        propagate untouched so the caller sees the real cause.
        """

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(
                        text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
                    )

                    total: int
                    if plan.count_sql is not None:
                        count_result = await session.execute(
                            text(plan.count_sql),
                            plan.count_params or {},
                        )
                        total = int(count_result.scalar() or 0)
                    else:
                        total = -1  # sentinel: fill in from row count below

                    data_result = await session.execute(
                        text(plan.sql),
                        plan.params or {},
                    )
                    rows = [dict(row) for row in data_result.mappings().all()]

                    if total == -1:
                        total = len(rows)

                    return rows, total
        except DBAPIError as exc:
            if _is_query_canceled(exc):
                log.warning(
                    "uql.query_timeout",
                    timeout_ms=STATEMENT_TIMEOUT_MS,
                )
                raise uql_errors.UQLError(
                    uql_errors.QUERY_TIMEOUT,
                    f"Query exceeded {STATEMENT_TIMEOUT_MS}ms statement timeout",
                    "Narrow the filters, reduce the limit, "
                    "or use an aggregation/timeseries template "
                    "instead of a wide snapshot.",
                ) from exc
            raise

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
