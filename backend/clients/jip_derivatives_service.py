"""JIP client for derivatives (F&O) and macro/VIX data.

Reads from de_fo_bhavcopy, de_fo_summary, de_participant_oi, de_macro_values.
Never writes. All SQL via SQLAlchemy session.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

_FO_STALENESS_DAYS = 5  # after weekends/holidays
_VIX_STALENESS_DAYS = 5


class JIPDerivativesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_fo_health(self) -> tuple[bool, str]:
        """Return (is_healthy, reason). reason='' if healthy."""
        result = await self._session.execute(
            text("SELECT COUNT(*), MAX(trade_date) FROM de_fo_bhavcopy")
        )
        row = result.fetchone()
        count: int = row[0] or 0 if row is not None else 0
        max_date: date | None = row[1] if row is not None else None
        if count == 0:
            return False, "derivatives_eod:freshness=0 (de_fo_bhavcopy has no data)"
        if max_date is None:
            return False, "derivatives_eod:freshness=0 (de_fo_bhavcopy max date is NULL)"
        lag = (datetime.now(UTC).date() - max_date).days
        if lag > _FO_STALENESS_DAYS:
            return False, (
                f"derivatives_eod:freshness=stale (last trade_date={max_date}, lag={lag}d)"
            )
        return True, ""

    async def get_pcr_series(
        self, symbol: str, from_date: date, to_date: date
    ) -> tuple[list[dict[str, Any]], str]:
        """Get PCR time series. Returns (rows, source).

        Tries de_fo_summary first (pre-computed), falls back to computing from
        de_fo_bhavcopy.
        """
        sym = symbol.upper()
        # Try de_fo_summary
        result = await self._session.execute(
            text(
                """
                SELECT date AS trade_date, pcr_oi, pcr_volume, total_oi
                FROM de_fo_summary
                WHERE date BETWEEN :from_date AND :to_date
                ORDER BY date DESC
                """
            ),
            {"from_date": from_date, "to_date": to_date},
        )
        rows = result.mappings().all()
        if rows:
            return [dict(r) for r in rows], "fo_summary"

        # Fallback: compute from de_fo_bhavcopy
        result = await self._session.execute(
            text(
                """
                WITH oi_by_type AS (
                    SELECT
                        trade_date,
                        SUM(CASE WHEN option_type = 'PE' THEN open_interest ELSE 0 END)
                            AS put_oi,
                        SUM(CASE WHEN option_type = 'CE' THEN open_interest ELSE 0 END)
                            AS call_oi
                    FROM de_fo_bhavcopy
                    WHERE symbol = :symbol
                      AND trade_date BETWEEN :from_date AND :to_date
                      AND instrument_type IN ('OPTIDX', 'OPTSTK')
                    GROUP BY trade_date
                )
                SELECT
                    trade_date,
                    CASE WHEN call_oi > 0
                         THEN (put_oi::numeric / NULLIF(call_oi, 0))
                         ELSE NULL END AS pcr_oi,
                    NULL::numeric AS pcr_volume,
                    (put_oi + call_oi) AS total_oi
                FROM oi_by_type
                ORDER BY trade_date DESC
                """
            ),
            {"symbol": sym, "from_date": from_date, "to_date": to_date},
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows], "fo_bhavcopy_computed"

    async def get_oi_buildup(
        self, symbol: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        """OI buildup chart: daily OI + change aggregated across expiries, by option_type."""
        sym = symbol.upper()
        result = await self._session.execute(
            text(
                """
                SELECT
                    trade_date,
                    option_type,
                    SUM(open_interest)  AS total_oi,
                    SUM(change_in_oi)   AS change_in_oi
                FROM de_fo_bhavcopy
                WHERE symbol = :symbol
                  AND trade_date BETWEEN :from_date AND :to_date
                GROUP BY trade_date, option_type
                ORDER BY trade_date, option_type
                """
            ),
            {"symbol": sym, "from_date": from_date, "to_date": to_date},
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]

    async def check_vix_health(self) -> tuple[bool, str]:
        """Return (is_healthy, reason). reason='' if healthy."""
        result = await self._session.execute(
            text(
                """
                SELECT COUNT(*), MAX(date)
                FROM de_macro_values
                WHERE ticker = 'INDIAVIX'
                """
            )
        )
        row = result.fetchone()
        count: int = row[0] or 0 if row is not None else 0
        max_date: date | None = row[1] if row is not None else None
        if count == 0:
            return False, "india_vix:freshness=0 (no INDIAVIX rows in de_macro_values)"
        if max_date is None:
            return False, "india_vix:freshness=0 (INDIAVIX max date is NULL)"
        lag = (datetime.now(UTC).date() - max_date).days
        if lag > _VIX_STALENESS_DAYS:
            return False, (f"india_vix:freshness=stale (last date={max_date}, lag={lag}d)")
        return True, ""

    async def get_india_vix(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        """Get India VIX series from de_macro_values."""
        result = await self._session.execute(
            text(
                """
                SELECT date AS trade_date, value AS close
                FROM de_macro_values
                WHERE ticker = 'INDIAVIX'
                  AND date BETWEEN :from_date AND :to_date
                ORDER BY date
                """
            ),
            {"from_date": from_date, "to_date": to_date},
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]
