"""JIP client for macro data: yield curve, FX rates, RBI policy rates.

Reads from:
  - de_gsec_yield         (CCIL G-Sec yield curve by tenor)
  - de_rbi_fx_rate        (RBI reference FX rates)
  - de_rbi_policy_rate    (RBI policy rates: REPO, REVERSE_REPO, CRR, SLR, BANK_RATE)

Never writes. All SQL via SQLAlchemy async session.
Returns 503 reason strings from health checks when tables are empty or stale.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

_STALENESS_DAYS = 5  # daily data; weekends + holidays can add up to ~3 days


class JIPMacroService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Yield curve (de_gsec_yield)
    # ------------------------------------------------------------------

    async def check_yield_health(self) -> tuple[bool, str]:
        """Return (is_healthy, reason). reason='' if healthy."""
        qr = await self._session.execute(
            text("SELECT COUNT(*), MAX(yield_date) FROM de_gsec_yield")
        )
        row = qr.fetchone()
        count: int = row[0] or 0 if row is not None else 0
        max_date: Optional[date] = row[1] if row is not None else None
        if count == 0:
            return False, "yield_curve:freshness=0 (de_gsec_yield has no data)"
        if max_date is None:
            return False, "yield_curve:freshness=0 (de_gsec_yield max date is NULL)"
        lag = (datetime.now(UTC).date() - max_date).days
        if lag > _STALENESS_DAYS:
            return False, (f"yield_curve:freshness=stale (last yield_date={max_date}, lag={lag}d)")
        return True, ""

    async def get_yield_curve(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        """Return yield curve rows ordered by date then tenor.

        Each row: yield_date, tenor, yield_pct, security_name, source.
        """
        qr = await self._session.execute(
            text(
                """
                SELECT yield_date, tenor, yield_pct, security_name, source
                FROM de_gsec_yield
                WHERE yield_date BETWEEN :from_date AND :to_date
                ORDER BY yield_date, tenor
                """
            ),
            {"from_date": from_date, "to_date": to_date},
        )
        rows = qr.mappings().all()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # FX rates (de_rbi_fx_rate)
    # ------------------------------------------------------------------

    async def check_fx_health(self) -> tuple[bool, str]:
        """Return (is_healthy, reason). reason='' if healthy."""
        qr = await self._session.execute(
            text("SELECT COUNT(*), MAX(rate_date) FROM de_rbi_fx_rate")
        )
        row = qr.fetchone()
        count: int = row[0] or 0 if row is not None else 0
        max_date: Optional[date] = row[1] if row is not None else None
        if count == 0:
            return False, "fx_rates:freshness=0 (de_rbi_fx_rate has no data)"
        if max_date is None:
            return False, "fx_rates:freshness=0 (de_rbi_fx_rate max date is NULL)"
        lag = (datetime.now(UTC).date() - max_date).days
        if lag > _STALENESS_DAYS:
            return False, (f"fx_rates:freshness=stale (last rate_date={max_date}, lag={lag}d)")
        return True, ""

    async def get_fx_rates(
        self,
        from_date: date,
        to_date: date,
        currency_pair: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return FX rate rows ordered by date then currency_pair.

        Each row: rate_date, currency_pair, reference_rate, source.
        Optionally filter by currency_pair (e.g. 'USD/INR').
        """
        if currency_pair is not None:
            qr = await self._session.execute(
                text(
                    """
                    SELECT rate_date, currency_pair, reference_rate, source
                    FROM de_rbi_fx_rate
                    WHERE rate_date BETWEEN :from_date AND :to_date
                      AND currency_pair = :pair
                    ORDER BY rate_date, currency_pair
                    """
                ),
                {"from_date": from_date, "to_date": to_date, "pair": currency_pair.upper()},
            )
        else:
            qr = await self._session.execute(
                text(
                    """
                    SELECT rate_date, currency_pair, reference_rate, source
                    FROM de_rbi_fx_rate
                    WHERE rate_date BETWEEN :from_date AND :to_date
                    ORDER BY rate_date, currency_pair
                    """
                ),
                {"from_date": from_date, "to_date": to_date},
            )
        rows = qr.mappings().all()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # RBI policy rates (de_rbi_policy_rate)
    # ------------------------------------------------------------------

    async def check_policy_health(self) -> tuple[bool, str]:
        """Return (is_healthy, reason). reason='' if healthy."""
        qr = await self._session.execute(
            text("SELECT COUNT(*), MAX(effective_date) FROM de_rbi_policy_rate")
        )
        row = qr.fetchone()
        count: int = row[0] or 0 if row is not None else 0
        max_date: Optional[date] = row[1] if row is not None else None
        if count == 0:
            return False, "policy_rates:freshness=0 (de_rbi_policy_rate has no data)"
        if max_date is None:
            return False, "policy_rates:freshness=0 (de_rbi_policy_rate max date is NULL)"
        lag = (datetime.now(UTC).date() - max_date).days
        if lag > _STALENESS_DAYS:
            return False, (
                f"policy_rates:freshness=stale (last effective_date={max_date}, lag={lag}d)"
            )
        return True, ""

    async def get_policy_rates(
        self,
        from_date: date,
        to_date: date,
        rate_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return policy rate rows ordered by date then rate_type.

        Each row: effective_date, rate_type, rate_pct, source.
        Optionally filter by rate_type (e.g. 'REPO').
        """
        if rate_type is not None:
            qr = await self._session.execute(
                text(
                    """
                    SELECT effective_date, rate_type, rate_pct, source
                    FROM de_rbi_policy_rate
                    WHERE effective_date BETWEEN :from_date AND :to_date
                      AND rate_type = :rate_type
                    ORDER BY effective_date, rate_type
                    """
                ),
                {
                    "from_date": from_date,
                    "to_date": to_date,
                    "rate_type": rate_type.upper(),
                },
            )
        else:
            qr = await self._session.execute(
                text(
                    """
                    SELECT effective_date, rate_type, rate_pct, source
                    FROM de_rbi_policy_rate
                    WHERE effective_date BETWEEN :from_date AND :to_date
                    ORDER BY effective_date, rate_type
                    """
                ),
                {"from_date": from_date, "to_date": to_date},
            )
        rows = qr.mappings().all()
        return [dict(r) for r in rows]
