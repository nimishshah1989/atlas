"""JIP client for insider trades, bulk deals, and block deals.

Reads from de_insider_trades, de_bulk_deals, de_block_deals.
Never writes. All SQL via SQLAlchemy session.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

_STALENESS_DAYS = 5  # after weekends/holidays


class JIPInsiderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Insider trades (de_insider_trades)
    # ------------------------------------------------------------------

    async def check_insider_health(self) -> tuple[bool, str]:
        """Return (is_healthy, reason). reason='' if healthy."""
        qr = await self._session.execute(
            text("SELECT COUNT(*), MAX(txn_date) FROM de_insider_trades")
        )
        row = qr.fetchone()
        count: int = row[0] or 0 if row is not None else 0
        max_date: date | None = row[1] if row is not None else None
        if count == 0:
            return False, "insider_trades:freshness=0 (de_insider_trades has no data)"
        if max_date is None:
            return False, "insider_trades:freshness=0 (de_insider_trades max date is NULL)"
        lag = (datetime.now(UTC).date() - max_date).days
        if lag > _STALENESS_DAYS:
            return False, (f"insider_trades:freshness=stale (last txn_date={max_date}, lag={lag}d)")
        return True, ""

    async def get_insider_trades(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """SELECT from de_insider_trades for symbol in date range."""
        sym = symbol.upper()
        qr = await self._session.execute(
            text(
                """
                SELECT
                    symbol,
                    filing_date,
                    txn_date,
                    person_name,
                    person_category,
                    txn_type,
                    qty,
                    value_inr,
                    post_holding_pct
                FROM de_insider_trades
                WHERE symbol = :sym
                  AND txn_date BETWEEN :from_date AND :to_date
                ORDER BY txn_date DESC
                LIMIT :limit
                """
            ),
            {"sym": sym, "from_date": from_date, "to_date": to_date, "limit": limit},
        )
        rows = qr.mappings().all()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Bulk deals (de_bulk_deals)
    # ------------------------------------------------------------------

    async def check_bulk_health(self) -> tuple[bool, str]:
        """Return (is_healthy, reason). reason='' if healthy."""
        qr = await self._session.execute(
            text("SELECT COUNT(*), MAX(trade_date) FROM de_bulk_deals")
        )
        row = qr.fetchone()
        count: int = row[0] or 0 if row is not None else 0
        max_date: date | None = row[1] if row is not None else None
        if count == 0:
            return False, "bulk_deals:freshness=0 (de_bulk_deals has no data)"
        if max_date is None:
            return False, "bulk_deals:freshness=0 (de_bulk_deals max date is NULL)"
        lag = (datetime.now(UTC).date() - max_date).days
        if lag > _STALENESS_DAYS:
            return False, (f"bulk_deals:freshness=stale (last trade_date={max_date}, lag={lag}d)")
        return True, ""

    async def get_bulk_deals(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
    ) -> list[dict[str, Any]]:
        """SELECT from de_bulk_deals for symbol in date range."""
        sym = symbol.upper()
        qr = await self._session.execute(
            text(
                """
                SELECT
                    trade_date,
                    symbol,
                    client_name,
                    txn_type,
                    qty,
                    avg_price
                FROM de_bulk_deals
                WHERE symbol = :sym
                  AND trade_date BETWEEN :from_date AND :to_date
                ORDER BY trade_date DESC
                """
            ),
            {"sym": sym, "from_date": from_date, "to_date": to_date},
        )
        rows = qr.mappings().all()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Block deals (de_block_deals)
    # ------------------------------------------------------------------

    async def check_block_health(self) -> tuple[bool, str]:
        """Return (is_healthy, reason). reason='' if healthy."""
        qr = await self._session.execute(
            text("SELECT COUNT(*), MAX(trade_date) FROM de_block_deals")
        )
        row = qr.fetchone()
        count: int = row[0] or 0 if row is not None else 0
        max_date: date | None = row[1] if row is not None else None
        if count == 0:
            return False, "block_deals:freshness=0 (de_block_deals has no data)"
        if max_date is None:
            return False, "block_deals:freshness=0 (de_block_deals max date is NULL)"
        lag = (datetime.now(UTC).date() - max_date).days
        if lag > _STALENESS_DAYS:
            return False, (f"block_deals:freshness=stale (last trade_date={max_date}, lag={lag}d)")
        return True, ""

    async def get_block_deals(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
    ) -> list[dict[str, Any]]:
        """SELECT from de_block_deals for symbol in date range."""
        sym = symbol.upper()
        qr = await self._session.execute(
            text(
                """
                SELECT
                    trade_date,
                    symbol,
                    client_name,
                    txn_type,
                    qty,
                    trade_price
                FROM de_block_deals
                WHERE symbol = :sym
                  AND trade_date BETWEEN :from_date AND :to_date
                ORDER BY trade_date DESC
                """
            ),
            {"sym": sym, "from_date": from_date, "to_date": to_date},
        )
        rows = qr.mappings().all()
        return [dict(r) for r in rows]
