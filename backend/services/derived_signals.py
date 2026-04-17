"""Derived signal computations — query-time, read-only, no new DB writes.

C-DER-1 signals:
  - Gold RS: Stock return vs Gold (GLD ETF) return over a 63-day rolling window.
  - Piotroski F-Score: 9-point financial health checklist from annual fundamentals.

All financial arithmetic uses Decimal exclusively. Never float.
Both functions are fault-tolerant: they return None (or a sentinel) on
insufficient data rather than raising exceptions.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.schemas import (
    GoldRS,
    GoldRSSignal,
    Piotroski,
    PiotroskiDetail,
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Gold RS signal
# ---------------------------------------------------------------------------

_GOLD_RS_STOCK_SQL = text(
    """
    SELECT close_adj, date
    FROM de_equity_technical_daily
    WHERE instrument_id = :instrument_id
      AND date >= (
            SELECT MAX(date)
            FROM de_equity_technical_daily
            WHERE instrument_id = :instrument_id
          ) - INTERVAL '95 days'
    ORDER BY date DESC
    LIMIT 80
    """
)

_GOLD_RS_GLD_SQL = text(
    """
    SELECT close, date
    FROM de_global_price_daily
    WHERE ticker = 'GLD'
      AND date >= (
            SELECT MAX(date)
            FROM de_global_price_daily
            WHERE ticker = 'GLD'
          ) - INTERVAL '95 days'
    ORDER BY date DESC
    LIMIT 80
    """
)


def _classify_gold_rs(ratio: Decimal) -> GoldRSSignal:
    """Map a ratio value to the locked GoldRSSignal enum variant."""
    if ratio > Decimal("1.05"):
        return GoldRSSignal.AMPLIFIES_BULL
    if ratio >= Decimal("0.95"):
        return GoldRSSignal.NEUTRAL
    if ratio >= Decimal("0.85"):
        return GoldRSSignal.FRAGILE
    return GoldRSSignal.AMPLIFIES_BEAR


async def compute_gold_rs(
    instrument_id: UUID,
    db: AsyncSession,
    period_days: int = 63,
) -> Optional[GoldRS]:
    """Compute the Gold Relative Strength signal for a stock.

    Compares the stock's 63-day (default) return to GLD's return over the
    same window.  Returns None when data is insufficient; returns a
    NEUTRAL sentinel when GLD data is insufficient but stock data exists.

    Args:
        instrument_id: UUID of the equity instrument.
        db: Async SQLAlchemy session (read-only).
        period_days: Look-back period in trading days (default 63 ≈ 3 months).

    Returns:
        GoldRS instance or None.
    """
    # --- Stock prices ---
    stock_result = await db.execute(
        _GOLD_RS_STOCK_SQL,
        {"instrument_id": str(instrument_id)},
    )
    stock_rows = stock_result.fetchall()

    if len(stock_rows) < 30:
        log.warning(
            "gold_rs_insufficient_stock_data",
            instrument_id=str(instrument_id),
            row_count=len(stock_rows),
        )
        return None

    close_today = stock_rows[0][0]
    date_today: datetime.date = stock_rows[0][1]
    idx_63 = min(period_days, len(stock_rows) - 1)
    close_63d = stock_rows[idx_63][0]

    # --- GLD prices ---
    gld_result = await db.execute(_GOLD_RS_GLD_SQL, {})
    gld_rows = gld_result.fetchall()

    if len(gld_rows) < 30:
        log.warning(
            "gold_rs_insufficient_gld_data",
            row_count=len(gld_rows),
            instrument_id=str(instrument_id),
        )
        # Sentinel: return NEUTRAL when GLD data is missing
        return GoldRS(
            signal=GoldRSSignal.NEUTRAL,
            ratio_3m=None,
            stock_return_3m=None,
            gold_return_3m=None,
            as_of=date_today,
        )

    gld_today = gld_rows[0][0]
    gld_idx_63 = min(period_days, len(gld_rows) - 1)
    gld_63d = gld_rows[gld_idx_63][0]

    # --- Arithmetic (Decimal only) ---
    d_close_today = Decimal(str(close_today))
    d_close_63d = Decimal(str(close_63d))
    d_gld_today = Decimal(str(gld_today))
    d_gld_63d = Decimal(str(gld_63d))

    stock_return = (d_close_today - d_close_63d) / d_close_63d
    gold_return = (d_gld_today - d_gld_63d) / d_gld_63d

    denominator = Decimal("1") + gold_return
    if denominator == Decimal("0"):
        log.warning(
            "gold_rs_division_guard_triggered",
            instrument_id=str(instrument_id),
            gold_return=str(gold_return),
        )
        return None

    ratio = (Decimal("1") + stock_return) / denominator

    # Quantize to 4 decimal places
    quant = Decimal("0.0001")
    ratio_q = ratio.quantize(quant)
    stock_return_q = stock_return.quantize(quant)
    gold_return_q = gold_return.quantize(quant)

    return GoldRS(
        signal=_classify_gold_rs(ratio_q),
        ratio_3m=ratio_q,
        stock_return_3m=stock_return_q,
        gold_return_3m=gold_return_q,
        as_of=date_today,
    )


# ---------------------------------------------------------------------------
# Piotroski F-Score
# ---------------------------------------------------------------------------

_PIOTROSKI_HISTORY_SQL = text(
    """
    SELECT
        fiscal_period_end,
        net_profit_cr,
        cfo_cr,
        opm_pct,
        revenue_cr,
        total_assets_cr,
        borrowings_cr,
        equity_capital_cr,
        reserves_cr
    FROM de_equity_fundamentals_history
    WHERE instrument_id = :instrument_id
      AND period_type = 'annual'
    ORDER BY fiscal_period_end DESC
    LIMIT 3
    """
)

_PIOTROSKI_FUNDAMENTALS_SQL = text(
    """
    SELECT roe_pct, debt_to_equity
    FROM de_equity_fundamentals
    WHERE instrument_id = :instrument_id
    LIMIT 1
    """
)


def _total_equity(row: Any) -> Optional[Decimal]:
    """Compute total equity = equity_capital_cr + reserves_cr.

    Returns None if either field is NULL or if the total is zero
    (guards downstream division).

    Accepts both SQLAlchemy RowMapping objects and plain dicts.
    """
    # Use dict-style access (.get) which works for both RowMapping and dict
    if hasattr(row, "get"):
        eq_cap = row.get("equity_capital_cr")
        reserves = row.get("reserves_cr")
    else:
        eq_cap = getattr(row, "equity_capital_cr", None)
        reserves = getattr(row, "reserves_cr", None)
    if eq_cap is None or reserves is None:
        return None
    total = Decimal(str(eq_cap)) + Decimal(str(reserves))
    return total if total != Decimal("0") else None


def _grade(score: int) -> str:
    """Map a Piotroski score (0–9) to a grade string."""
    if score <= 2:
        return "WEAK"
    if score <= 5:
        return "NEUTRAL"
    if score <= 7:
        return "GOOD"
    return "STRONG"


async def compute_piotroski(
    instrument_id: UUID,
    db: AsyncSession,
) -> Optional[Piotroski]:
    """Compute the Piotroski F-Score for a stock.

    Uses the two most recent annual rows from de_equity_fundamentals_history
    and the point-in-time snapshot from de_equity_fundamentals.

    Returns None when no annual history rows are available.
    Returns a partial score (F3/F5/F7/F8/F9 = False) when only one history
    row exists (no prior-year comparison possible).

    Args:
        instrument_id: UUID of the equity instrument.
        db: Async SQLAlchemy session (read-only).

    Returns:
        Piotroski instance or None.
    """
    iid = str(instrument_id)

    # --- Annual history rows ---
    hist_result = await db.execute(
        _PIOTROSKI_HISTORY_SQL,
        {"instrument_id": iid},
    )
    hist_rows = hist_result.mappings().all()

    if len(hist_rows) == 0:
        log.warning(
            "piotroski_no_history_rows",
            instrument_id=iid,
        )
        return None

    latest = hist_rows[0]
    prior = hist_rows[1] if len(hist_rows) >= 2 else None

    # --- Point-in-time fundamentals ---
    fund_result = await db.execute(
        _PIOTROSKI_FUNDAMENTALS_SQL,
        {"instrument_id": iid},
    )
    fund_rows = fund_result.mappings().all()
    fundamentals = fund_rows[0] if fund_rows else None

    # -----------------------------------------------------------------------
    # F1: Profitability — net profit positive
    # -----------------------------------------------------------------------
    f1 = latest["net_profit_cr"] is not None and Decimal(str(latest["net_profit_cr"])) > Decimal(
        "0"
    )

    # -----------------------------------------------------------------------
    # F2: Cash flow from operations positive
    # -----------------------------------------------------------------------
    f2 = latest["cfo_cr"] is not None and Decimal(str(latest["cfo_cr"])) > Decimal("0")

    # -----------------------------------------------------------------------
    # F3: ROE improving (requires point-in-time fundamentals + prior year)
    # -----------------------------------------------------------------------
    f3 = False
    if prior is not None and fundamentals is not None:
        current_roe = fundamentals["roe_pct"]
        if current_roe is not None:
            prior_equity = _total_equity(prior)
            if prior_equity is not None and prior["net_profit_cr"] is not None:
                prior_roe = Decimal(str(prior["net_profit_cr"])) / prior_equity * Decimal("100")
                f3 = Decimal(str(current_roe)) > prior_roe

    # -----------------------------------------------------------------------
    # F4: Quality earnings — CFO > net profit (accruals check)
    # -----------------------------------------------------------------------
    f4 = False
    if latest["cfo_cr"] is not None and latest["net_profit_cr"] is not None:
        f4 = Decimal(str(latest["cfo_cr"])) > Decimal(str(latest["net_profit_cr"]))

    # -----------------------------------------------------------------------
    # F5: Leverage falling (requires point-in-time D/E + prior year)
    # -----------------------------------------------------------------------
    f5 = False
    if prior is not None and fundamentals is not None:
        current_de = fundamentals["debt_to_equity"]
        if current_de is not None:
            prior_equity = _total_equity(prior)
            if prior_equity is not None and prior["borrowings_cr"] is not None:
                prior_de = Decimal(str(prior["borrowings_cr"])) / prior_equity
                f5 = Decimal(str(current_de)) < prior_de

    # -----------------------------------------------------------------------
    # F6: Liquidity improving — CFO / borrowings ratio improving
    # -----------------------------------------------------------------------
    f6 = False
    if prior is not None:
        lat_cfo = latest["cfo_cr"]
        lat_bor = latest["borrowings_cr"]
        pri_cfo = prior["cfo_cr"]
        pri_bor = prior["borrowings_cr"]
        if (
            lat_cfo is not None
            and lat_bor is not None
            and pri_cfo is not None
            and pri_bor is not None
            and Decimal(str(lat_bor)) != Decimal("0")
            and Decimal(str(pri_bor)) != Decimal("0")
        ):
            curr_ratio = Decimal(str(lat_cfo)) / Decimal(str(lat_bor))
            prior_ratio = Decimal(str(pri_cfo)) / Decimal(str(pri_bor))
            f6 = curr_ratio > prior_ratio

    # -----------------------------------------------------------------------
    # F7: No dilution — equity capital not increased
    # -----------------------------------------------------------------------
    f7 = False
    if prior is not None:
        lat_eq = latest["equity_capital_cr"]
        pri_eq = prior["equity_capital_cr"]
        if lat_eq is not None and pri_eq is not None:
            f7 = Decimal(str(lat_eq)) <= Decimal(str(pri_eq))

    # -----------------------------------------------------------------------
    # F8: Gross margin expanding (OPM improving)
    # -----------------------------------------------------------------------
    f8 = False
    if prior is not None:
        lat_opm = latest["opm_pct"]
        pri_opm = prior["opm_pct"]
        if lat_opm is not None and pri_opm is not None:
            f8 = Decimal(str(lat_opm)) > Decimal(str(pri_opm))

    # -----------------------------------------------------------------------
    # F9: Asset turnover improving (revenue/total_assets)
    # -----------------------------------------------------------------------
    f9 = False
    if prior is not None:
        lat_rev = latest["revenue_cr"]
        lat_ta = latest["total_assets_cr"]
        pri_rev = prior["revenue_cr"]
        pri_ta = prior["total_assets_cr"]
        if (
            lat_rev is not None
            and lat_ta is not None
            and pri_rev is not None
            and pri_ta is not None
            and Decimal(str(lat_ta)) != Decimal("0")
            and Decimal(str(pri_ta)) != Decimal("0")
        ):
            curr_turnover = Decimal(str(lat_rev)) / Decimal(str(lat_ta))
            prior_turnover = Decimal(str(pri_rev)) / Decimal(str(pri_ta))
            f9 = curr_turnover > prior_turnover

    # -----------------------------------------------------------------------
    # Aggregate
    # -----------------------------------------------------------------------
    score = sum(int(b) for b in [f1, f2, f3, f4, f5, f6, f7, f8, f9])
    detail = PiotroskiDetail(
        f1_net_profit_positive=f1,
        f2_cfo_positive=f2,
        f3_roe_improving=f3,
        f4_quality_earnings=f4,
        f5_leverage_falling=f5,
        f6_liquidity_improving=f6,
        f7_no_dilution=f7,
        f8_margin_expanding=f8,
        f9_asset_turnover_improving=f9,
    )

    as_of: Optional[datetime.date] = latest["fiscal_period_end"]

    return Piotroski(
        score=score,
        grade=_grade(score),
        detail=detail,
        as_of=as_of,
    )
