"""GoldRSService — V7-0: Gold Relative Strength computation service.

Computes how an entity (stock, ETF, sector) performs relative to gold
over 1m, 3m, 6m, and 12m windows.

All arithmetic uses Decimal exclusively. Never float.
Returns None when data is insufficient — never 0, never NaN.

Data source: de_global_price_daily (read-only JIP table)
  - USD gold: ticker='GLD'
  - INR gold: ticker='GOLDBEES'

Formula per period (n trading days):
  instrument_return_pct = (last - prev_n) / prev_n * 100
  gold_return_pct       = (last_gold - prev_n_gold) / prev_n_gold * 100
  rs_vs_gold            = instrument_return_pct - gold_return_pct

Signal classification (strict inequalities — zero falls through to FRAGILE):
  STALE              — gold_missing AND yesterday_age_days > 2
  AMPLIFIES_BULL     — rs_benchmark > 0 AND rs_gold > 0
  AMPLIFIES_BEAR     — rs_benchmark < 0 AND rs_gold < 0
  NEUTRAL_BENCH_ONLY — rs_benchmark > 0 AND rs_gold < 0
  FRAGILE            — all other cases (incl. None, exact zeros)
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

# Default period windows in trading days
DEFAULT_PERIODS: dict[str, int] = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}

# Ticker mapping by currency
_GOLD_TICKER: dict[str, str] = {
    "USD": "GLD",
    "INR": "GOLDBEES",
}


def _to_decimal(value: object) -> Optional[Decimal]:
    """Convert a DB value to Decimal via str() round-trip.

    Returns None on None input or conversion failure.
    Never raises; never returns float.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


class GoldRSService:
    """Service for computing Gold RS (Relative Strength vs Gold).

    Plain class — no async __init__. Use get_gold_price_series() in async context.
    All public methods are pure computation except get_gold_price_series.
    """

    async def get_gold_price_series(
        self,
        session: AsyncSession,
        start: datetime.date,
        end: datetime.date,
        currency: Literal["INR", "USD"] = "USD",
    ) -> list[tuple[datetime.date, Decimal]]:
        """Fetch gold price series from de_global_price_daily.

        Args:
            session: Async SQLAlchemy session (read-only).
            start: Start date (inclusive).
            end: End date (inclusive).
            currency: "USD" → ticker='GLD', "INR" → ticker='GOLDBEES'.

        Returns:
            List of (date, Decimal(close)) sorted ascending.
            Empty list if no data in range.
            Rows with NULL close are silently skipped.
        """
        ticker = _GOLD_TICKER.get(currency, "GLD")
        sql = text(
            """
            SELECT date, close
            FROM de_global_price_daily
            WHERE ticker = :ticker
              AND date >= :start
              AND date <= :end
              AND close IS NOT NULL
            ORDER BY date ASC
            """
        )
        db_result = await session.execute(sql, {"ticker": ticker, "start": start, "end": end})
        rows = db_result.fetchall()
        log.debug(
            "gold_price_series_fetched",
            ticker=ticker,
            start=str(start),
            end=str(end),
            row_count=len(rows),
        )

        series: list[tuple[datetime.date, Decimal]] = []
        for row in rows:
            price = _to_decimal(row[1])
            if price is not None:
                series.append((row[0], price))

        return series

    def compute_rs_vs_gold(
        self,
        instrument_series: list[tuple[datetime.date, Decimal]],
        gold_series: list[tuple[datetime.date, Decimal]],
        periods_days: dict[str, int],
    ) -> dict[str, Optional[Decimal]]:
        """Compute RS vs gold for each period window.

        Args:
            instrument_series: List of (date, price) for the instrument, any order.
            gold_series:       List of (date, price) for gold, any order.
            periods_days:      Dict mapping period label → number of trading days.
                               e.g. {"1m": 21, "3m": 63, "6m": 126, "12m": 252}

        Returns:
            Dict mapping period label → Decimal RS (pct pts) or None if insufficient data.
            None means not enough aligned data — never 0, never NaN.

        Algorithm per period (n days):
            1. Align both series to the intersection of dates present in BOTH.
            2. Sort by date ascending.
            3. Need at least n+1 aligned points.
            4. instrument_return = (last - prev_n) / prev_n * 100  [Decimal]
            5. gold_return       = (last - prev_n) / prev_n * 100  [Decimal]
            6. rs = instrument_return - gold_return
        """
        # Build lookup dicts for fast intersection
        instrument_map: dict[datetime.date, Decimal] = {d: p for d, p in instrument_series}
        gold_map: dict[datetime.date, Decimal] = {d: p for d, p in gold_series}

        # Intersection of dates present in BOTH series
        common_dates = sorted(instrument_map.keys() & gold_map.keys())

        rs_by_period: dict[str, Optional[Decimal]] = {}

        for period_key, n_days in periods_days.items():
            # Need at least n_days + 1 aligned points
            if len(common_dates) < n_days + 1:
                rs_by_period[period_key] = None
                log.debug(
                    "gold_rs_insufficient_data",
                    period=period_key,
                    needed=n_days + 1,
                    available=len(common_dates),
                )
                continue

            # Use the last n_days+1 aligned dates
            relevant = common_dates[-(n_days + 1) :]
            oldest_dt = relevant[0]
            newest_dt = relevant[-1]

            price_instrument_old = instrument_map[oldest_dt]
            price_instrument_new = instrument_map[newest_dt]
            price_gold_old = gold_map[oldest_dt]
            price_gold_new = gold_map[newest_dt]

            # Guard against zero-price division
            if price_instrument_old == Decimal("0") or price_gold_old == Decimal("0"):
                rs_by_period[period_key] = None
                log.warning(
                    "gold_rs_zero_price_guard",
                    period=period_key,
                    instrument_old=str(price_instrument_old),
                    gold_old=str(price_gold_old),
                )
                continue

            # Compute percentage returns — all Decimal arithmetic
            hundred = Decimal("100")
            instrument_return_pct = (
                (price_instrument_new - price_instrument_old) / price_instrument_old * hundred
            )
            gold_return_pct = (price_gold_new - price_gold_old) / price_gold_old * hundred
            rs = instrument_return_pct - gold_return_pct

            rs_by_period[period_key] = rs
            log.debug(
                "gold_rs_computed",
                period=period_key,
                instrument_return=str(instrument_return_pct),
                gold_return=str(gold_return_pct),
                rs=str(rs),
            )

        return rs_by_period

    def compute_gold_rs_signal(
        self,
        rs_benchmark: Optional[Decimal],
        rs_gold: Optional[Decimal],
        gold_missing: bool,
        yesterday_age_days: int,
    ) -> str:
        """Classify the gold RS signal.

        Args:
            rs_benchmark:     Stock RS vs market benchmark (e.g. from de_rs_scores).
                              Positive = outperforming benchmark.
            rs_gold:          rs_vs_gold_1m from compute_rs_vs_gold.
                              Positive = outperforming gold.
            gold_missing:     True when no gold price data is available.
            yesterday_age_days: Calendar days since last available gold price.

        Returns:
            One of: STALE, AMPLIFIES_BULL, AMPLIFIES_BEAR, NEUTRAL_BENCH_ONLY, FRAGILE

        Signal logic (strict inequalities — exact zeros fall to FRAGILE):
            STALE              — gold_missing AND yesterday_age_days > 2
            AMPLIFIES_BULL     — bench > 0 AND gold_rs > 0
            AMPLIFIES_BEAR     — bench < 0 AND gold_rs < 0
            NEUTRAL_BENCH_ONLY — bench > 0 AND gold_rs < 0
            FRAGILE            — everything else (incl. None, exact zeros, bench<0+gold>0)
        """
        # STALE: gold data too old to be trusted
        if gold_missing and yesterday_age_days > 2:
            return "STALE"

        # Classification requires both values — None → FRAGILE
        if rs_benchmark is None or rs_gold is None:
            return "FRAGILE"

        # Strict inequalities — zero boundary falls through to FRAGILE
        if rs_benchmark > Decimal("0") and rs_gold > Decimal("0"):
            return "AMPLIFIES_BULL"

        if rs_benchmark < Decimal("0") and rs_gold < Decimal("0"):
            return "AMPLIFIES_BEAR"

        if rs_benchmark > Decimal("0") and rs_gold < Decimal("0"):
            return "NEUTRAL_BENCH_ONLY"

        # rs_benchmark < 0 and rs_gold > 0, or any exact zero → FRAGILE
        return "FRAGILE"
