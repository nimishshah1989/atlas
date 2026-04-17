"""Unit tests for derived_signals.py — Gold RS + Piotroski computations.

All tests use AsyncMock for the DB session. No real database calls.
Pattern: mock session.execute via side_effect list for multi-call functions.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.models.schemas import GoldRSSignal
from backend.services.derived_signals import (
    compute_gold_rs,
    compute_piotroski,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(side_effects: list[Any]) -> AsyncMock:
    """Create a mock AsyncSession whose execute() returns results in sequence."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=side_effects)
    return session


def _stock_result(rows: list[tuple[Any, datetime.date]]) -> MagicMock:
    """Build a mock fetchall-style result for stock price queries."""
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _gld_result(rows: list[tuple[Any, datetime.date]]) -> MagicMock:
    """Build a mock fetchall-style result for GLD price queries."""
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _mapping_result(rows: list[dict[str, Any]]) -> MagicMock:
    """Build a mock mappings().all() style result for fundamentals queries."""
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _price_rows(
    today_price: float,
    prior_price: float,
    n: int = 65,
    offset_days: int = 63,
) -> list[tuple[Any, datetime.date]]:
    """Generate n price rows: row[0]=today, row[offset_days]=prior price."""
    base_date = datetime.date(2026, 4, 14)
    rows = []
    for i in range(n):
        if i == 0:
            price = today_price
        elif i == offset_days:
            price = prior_price
        else:
            price = today_price - (i * 0.01)
        rows.append((price, base_date - datetime.timedelta(days=i)))
    return rows


# ---------------------------------------------------------------------------
# Gold RS tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gold_rs_amplifies_bull_when_stock_beats_gold_by_5pct() -> None:
    """stock=+0.20, gold=+0.10 → ratio ≈ 1.091 → AMPLIFIES_BULL."""
    stock_rows = _price_rows(120.0, 100.0)  # +20% return
    gld_rows = _price_rows(110.0, 100.0)  # +10% return
    session = _make_session([_stock_result(stock_rows), _gld_result(gld_rows)])

    result = await compute_gold_rs(uuid4(), session)

    assert result is not None
    assert result.signal == GoldRSSignal.AMPLIFIES_BULL
    assert result.ratio_3m is not None
    assert result.ratio_3m > Decimal("1.05")


@pytest.mark.asyncio
async def test_gold_rs_neutral_within_band() -> None:
    """stock=+0.10, gold=+0.10 → ratio=1.00 → NEUTRAL."""
    stock_rows = _price_rows(110.0, 100.0)  # +10% return
    gld_rows = _price_rows(110.0, 100.0)  # +10% return
    session = _make_session([_stock_result(stock_rows), _gld_result(gld_rows)])

    result = await compute_gold_rs(uuid4(), session)

    assert result is not None
    assert result.signal == GoldRSSignal.NEUTRAL
    # ratio = (1.10)/(1.10) = 1.0
    assert result.ratio_3m == Decimal("1.0000")


@pytest.mark.asyncio
async def test_gold_rs_fragile_below_band() -> None:
    """stock=+0.05, gold=+0.15 → ratio ≈ 0.913 → FRAGILE."""
    stock_rows = _price_rows(105.0, 100.0)  # +5% return
    gld_rows = _price_rows(115.0, 100.0)  # +15% return
    session = _make_session([_stock_result(stock_rows), _gld_result(gld_rows)])

    result = await compute_gold_rs(uuid4(), session)

    assert result is not None
    assert result.signal == GoldRSSignal.FRAGILE
    # ratio = 1.05/1.15 ≈ 0.9130
    assert result.ratio_3m is not None
    assert Decimal("0.85") <= result.ratio_3m < Decimal("0.95")


@pytest.mark.asyncio
async def test_gold_rs_amplifies_bear_severely_underperforms() -> None:
    """stock=-0.20, gold=+0.10 → ratio ≈ 0.727 → AMPLIFIES_BEAR."""
    stock_rows = _price_rows(80.0, 100.0)  # -20% return
    gld_rows = _price_rows(110.0, 100.0)  # +10% return
    session = _make_session([_stock_result(stock_rows), _gld_result(gld_rows)])

    result = await compute_gold_rs(uuid4(), session)

    assert result is not None
    assert result.signal == GoldRSSignal.AMPLIFIES_BEAR
    # ratio = 0.80/1.10 ≈ 0.7273
    assert result.ratio_3m is not None
    assert result.ratio_3m < Decimal("0.85")


@pytest.mark.asyncio
async def test_gold_rs_handles_missing_gld_data_returns_neutral_sentinel() -> None:
    """GLD=5 rows → GoldRS(signal=NEUTRAL, ratio_3m=None), NOT None."""
    stock_rows = _price_rows(110.0, 100.0)  # 65 rows — sufficient
    gld_rows = _price_rows(110.0, 100.0, n=5)  # only 5 rows — insufficient
    session = _make_session([_stock_result(stock_rows), _gld_result(gld_rows)])

    result = await compute_gold_rs(uuid4(), session)

    # Must NOT be None — should be a sentinel with NEUTRAL signal
    assert result is not None
    assert result.signal == GoldRSSignal.NEUTRAL
    assert result.ratio_3m is None
    assert result.stock_return_3m is None
    assert result.gold_return_3m is None


@pytest.mark.asyncio
async def test_gold_rs_handles_missing_stock_data_returns_none() -> None:
    """Stock=0 rows → None (not a sentinel)."""
    stock_rows: list[tuple[Any, datetime.date]] = []
    session = _make_session([_stock_result(stock_rows)])

    result = await compute_gold_rs(uuid4(), session)

    assert result is None


@pytest.mark.asyncio
async def test_gold_rs_ratio_uses_3m_period_default() -> None:
    """Default period_days=63 is used when not specified."""
    stock_rows = _price_rows(120.0, 100.0)
    gld_rows = _price_rows(110.0, 100.0)
    session = _make_session([_stock_result(stock_rows), _gld_result(gld_rows)])

    # Call without period_days — should default to 63
    result = await compute_gold_rs(uuid4(), session)

    assert result is not None
    # With period_days=63, idx_63 = 63, so row[63] = prior
    # stock: row[63] = 100.0 → stock_return = (120-100)/100 = 0.20
    assert result.stock_return_3m is not None


@pytest.mark.asyncio
async def test_gold_rs_uses_close_adj_not_close() -> None:
    """Verify that the stock price SQL uses 'close_adj', not 'close'."""
    from backend.services.derived_signals import _GOLD_RS_STOCK_SQL

    sql_text = str(_GOLD_RS_STOCK_SQL)
    assert "close_adj" in sql_text, "Stock price SQL must use close_adj, not close"
    assert "close_adj" in sql_text


@pytest.mark.asyncio
async def test_gold_rs_division_guard_gold_return_minus_one() -> None:
    """gld_today=0, gld_63d=100 → denominator=0 → returns None."""
    stock_rows = _price_rows(120.0, 100.0)
    # GLD goes to 0 from 100 → gold_return = -1.0, denominator = 0
    base_date = datetime.date(2026, 4, 14)
    gld_rows = [(0.0, base_date)]
    # Need at least 30 rows
    for i in range(1, 65):
        gld_rows.append((100.0, base_date - datetime.timedelta(days=i)))
    session = _make_session([_stock_result(stock_rows), _gld_result(gld_rows)])

    result = await compute_gold_rs(uuid4(), session)

    assert result is None, "Division guard must return None when gold_return == -1"


# ---------------------------------------------------------------------------
# Piotroski tests — helper row factory
# ---------------------------------------------------------------------------


def _hist_row(
    net_profit_cr: Any = 100,
    cfo_cr: Any = 120,
    opm_pct: Any = 15,
    revenue_cr: Any = 1000,
    total_assets_cr: Any = 500,
    borrowings_cr: Any = 200,
    equity_capital_cr: Any = 50,
    reserves_cr: Any = 350,
    fiscal_period_end: Any = None,
) -> dict[str, Any]:
    """Create a history row dict with sensible defaults."""
    return {
        "fiscal_period_end": fiscal_period_end or datetime.date(2025, 3, 31),
        "net_profit_cr": net_profit_cr,
        "cfo_cr": cfo_cr,
        "opm_pct": opm_pct,
        "revenue_cr": revenue_cr,
        "total_assets_cr": total_assets_cr,
        "borrowings_cr": borrowings_cr,
        "equity_capital_cr": equity_capital_cr,
        "reserves_cr": reserves_cr,
    }


def _fund_row(roe_pct: Any = 25.0, debt_to_equity: Any = 0.4) -> dict[str, Any]:
    """Create a point-in-time fundamentals row dict."""
    return {"roe_pct": roe_pct, "debt_to_equity": debt_to_equity}


# ---------------------------------------------------------------------------
# Piotroski tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_piotroski_perfect_score_returns_9_strong() -> None:
    """All 9 checks pass → score==9, grade=='STRONG'."""
    # Latest: strong profitability
    latest = _hist_row(
        net_profit_cr=100,  # F1: positive
        cfo_cr=120,  # F2: positive, F4: cfo > profit
        opm_pct=20,  # F8: > prior 15
        revenue_cr=1200,  # F9: 1200/500=2.4 > prior 800/500=1.6
        total_assets_cr=500,
        borrowings_cr=150,  # F6: cfo/bor=0.8 > prior 80/200=0.4
        equity_capital_cr=50,
        reserves_cr=350,
    )
    prior = _hist_row(
        net_profit_cr=80,
        cfo_cr=80,
        opm_pct=15,
        revenue_cr=800,
        total_assets_cr=500,
        borrowings_cr=200,
        equity_capital_cr=50,  # F7: same as latest → not increased
        reserves_cr=350,
    )
    fund = _fund_row(roe_pct=30.0, debt_to_equity=0.3)
    # prior_roe = 80 / (50+350) * 100 = 20, current=30 → F3=True
    # prior_de = 200 / (50+350) = 0.5, current=0.3 → F5=True

    session = _make_session(
        [
            _mapping_result([latest, prior]),
            _mapping_result([fund]),
        ]
    )

    result = await compute_piotroski(uuid4(), session)

    assert result is not None
    assert result.score == 9
    assert result.grade == "STRONG"
    assert result.detail.f1_net_profit_positive is True
    assert result.detail.f2_cfo_positive is True
    assert result.detail.f3_roe_improving is True
    assert result.detail.f4_quality_earnings is True
    assert result.detail.f5_leverage_falling is True
    assert result.detail.f6_liquidity_improving is True
    assert result.detail.f7_no_dilution is True
    assert result.detail.f8_margin_expanding is True
    assert result.detail.f9_asset_turnover_improving is True


@pytest.mark.asyncio
async def test_piotroski_zero_score_returns_0_weak() -> None:
    """All checks fail → score==0, grade=='WEAK'."""
    # Latest: all bad
    latest = _hist_row(
        net_profit_cr=-50,  # F1: negative
        cfo_cr=-20,  # F2: negative
        opm_pct=10,  # F8: < prior 15
        revenue_cr=500,  # F9: 500/500=1.0 < prior 1200/500=2.4
        total_assets_cr=500,
        borrowings_cr=300,  # F6: cfo/bor=-0.067 < prior 80/200=0.4
        equity_capital_cr=60,  # F7: > prior 50 → diluted
        reserves_cr=400,
    )
    prior = _hist_row(
        net_profit_cr=80,
        cfo_cr=80,
        opm_pct=15,
        revenue_cr=1200,
        total_assets_cr=500,
        borrowings_cr=200,
        equity_capital_cr=50,
        reserves_cr=350,
    )
    # F4: cfo=-20 < profit=-50 → False (but actually -20 > -50 is True)
    # Let's adjust: cfo=-100 < profit=-50 → False
    latest["cfo_cr"] = -100
    fund = _fund_row(roe_pct=5.0, debt_to_equity=0.8)
    # prior_roe = 80/(50+350)*100 = 20, current=5 → F3=False
    # prior_de = 200/(50+350) = 0.5, current=0.8 → F5=False

    session = _make_session(
        [
            _mapping_result([latest, prior]),
            _mapping_result([fund]),
        ]
    )

    result = await compute_piotroski(uuid4(), session)

    assert result is not None
    assert result.score == 0
    assert result.grade == "WEAK"


@pytest.mark.asyncio
async def test_piotroski_handles_missing_history_returns_none() -> None:
    """0 annual rows → None."""
    session = _make_session(
        [
            _mapping_result([]),
            _mapping_result([]),
        ]
    )

    result = await compute_piotroski(uuid4(), session)

    assert result is None


@pytest.mark.asyncio
async def test_piotroski_single_annual_row_partial_score() -> None:
    """1 annual row → Piotroski returned; F3/F5/F7/F8/F9 all False."""
    latest = _hist_row(
        net_profit_cr=100,  # F1: True
        cfo_cr=120,  # F2: True, F4: True (120>100)
    )
    fund = _fund_row(roe_pct=25.0, debt_to_equity=0.4)

    session = _make_session(
        [
            _mapping_result([latest]),  # only 1 history row
            _mapping_result([fund]),
        ]
    )

    result = await compute_piotroski(uuid4(), session)

    assert result is not None
    # F1, F2, F4 can be True
    assert result.detail.f1_net_profit_positive is True
    assert result.detail.f2_cfo_positive is True
    assert result.detail.f4_quality_earnings is True
    # F3/F5/F6/F7/F8/F9 require prior year → all False
    assert result.detail.f3_roe_improving is False
    assert result.detail.f5_leverage_falling is False
    assert result.detail.f6_liquidity_improving is False
    assert result.detail.f7_no_dilution is False
    assert result.detail.f8_margin_expanding is False
    assert result.detail.f9_asset_turnover_improving is False


@pytest.mark.asyncio
async def test_piotroski_f3_uses_total_equity_not_share_capital_only() -> None:
    """Semantic sentinel: prior equity=equity_capital+reserves, not equity_capital alone.

    prior.net_profit_cr=100, equity_capital_cr=10, reserves_cr=390
    → prior_roe = 100/(10+390)*100 = 25.0  (NOT 100/10*100 = 1000)

    F3=True when fundamentals.roe_pct=30 (>25)
    F3=False when fundamentals.roe_pct=20 (<25)
    """
    latest = _hist_row(net_profit_cr=120)
    prior = _hist_row(
        net_profit_cr=100,
        equity_capital_cr=10,
        reserves_cr=390,
        fiscal_period_end=datetime.date(2024, 3, 31),
    )

    # Case 1: current_roe=30 > prior_roe=25 → F3=True
    fund_true = _fund_row(roe_pct=30.0)
    session_true = _make_session(
        [
            _mapping_result([latest, prior]),
            _mapping_result([fund_true]),
        ]
    )
    result_true = await compute_piotroski(uuid4(), session_true)
    assert result_true is not None
    assert result_true.detail.f3_roe_improving is True, (
        "F3 should be True: prior_roe=25 (using total equity=400), current=30"
    )

    # Case 2: current_roe=20 < prior_roe=25 → F3=False
    fund_false = _fund_row(roe_pct=20.0)
    session_false = _make_session(
        [
            _mapping_result([latest, prior]),
            _mapping_result([fund_false]),
        ]
    )
    result_false = await compute_piotroski(uuid4(), session_false)
    assert result_false is not None
    assert result_false.detail.f3_roe_improving is False, (
        "F3 should be False: prior_roe=25 (using total equity=400), current=20"
    )


@pytest.mark.asyncio
async def test_piotroski_f4_quality_earnings_cfo_gt_profit() -> None:
    """cfo=100, profit=80 → F4=True; cfo=50, profit=80 → F4=False."""
    # Case 1: cfo > profit
    row_true = _hist_row(cfo_cr=100, net_profit_cr=80)
    session_true = _make_session(
        [
            _mapping_result([row_true]),
            _mapping_result([]),
        ]
    )
    result_true = await compute_piotroski(uuid4(), session_true)
    assert result_true is not None
    assert result_true.detail.f4_quality_earnings is True

    # Case 2: cfo < profit
    row_false = _hist_row(cfo_cr=50, net_profit_cr=80)
    session_false = _make_session(
        [
            _mapping_result([row_false]),
            _mapping_result([]),
        ]
    )
    result_false = await compute_piotroski(uuid4(), session_false)
    assert result_false is not None
    assert result_false.detail.f4_quality_earnings is False


@pytest.mark.asyncio
async def test_piotroski_f5_uses_total_equity_denominator() -> None:
    """Semantic sentinel: prior D/E uses (equity_capital + reserves) as denominator.

    prior borrowings=200, equity_capital=10, reserves=390
    → prior D/E = 200/(10+390) = 0.5

    F5=True when fundamentals.debt_to_equity=0.4 (<0.5)
    F5=False when fundamentals.debt_to_equity=0.6 (>0.5)
    """
    latest = _hist_row()
    prior = _hist_row(
        borrowings_cr=200,
        equity_capital_cr=10,
        reserves_cr=390,
        fiscal_period_end=datetime.date(2024, 3, 31),
    )

    # Case 1: current D/E=0.4 < prior=0.5 → F5=True
    fund_true = _fund_row(debt_to_equity=0.4)
    session_true = _make_session(
        [
            _mapping_result([latest, prior]),
            _mapping_result([fund_true]),
        ]
    )
    result_true = await compute_piotroski(uuid4(), session_true)
    assert result_true is not None
    assert result_true.detail.f5_leverage_falling is True, (
        "F5 should be True: prior_de=0.5 (using total equity=400), current=0.4"
    )

    # Case 2: current D/E=0.6 > prior=0.5 → F5=False
    fund_false = _fund_row(debt_to_equity=0.6)
    session_false = _make_session(
        [
            _mapping_result([latest, prior]),
            _mapping_result([fund_false]),
        ]
    )
    result_false = await compute_piotroski(uuid4(), session_false)
    assert result_false is not None
    assert result_false.detail.f5_leverage_falling is False, (
        "F5 should be False: prior_de=0.5 (using total equity=400), current=0.6"
    )


@pytest.mark.asyncio
async def test_piotroski_f6_uses_cfo_to_borrowings_proxy() -> None:
    """Semantic sentinel: F6 uses CFO/borrowings ratio.

    latest cfo=120, borrowings=100 → ratio=1.2
    prior  cfo=80,  borrowings=100 → ratio=0.8
    → curr > prior → F6=True

    If borrowings=0 in either period → F6=False.
    """
    # Case 1: improving ratio
    latest_ok = _hist_row(cfo_cr=120, borrowings_cr=100)
    prior_ok = _hist_row(cfo_cr=80, borrowings_cr=100)
    session_ok = _make_session(
        [
            _mapping_result([latest_ok, prior_ok]),
            _mapping_result([_fund_row()]),
        ]
    )
    result_ok = await compute_piotroski(uuid4(), session_ok)
    assert result_ok is not None
    assert result_ok.detail.f6_liquidity_improving is True

    # Case 2: borrowings=0 in latest → F6=False
    latest_zero = _hist_row(cfo_cr=120, borrowings_cr=0)
    prior_zero = _hist_row(cfo_cr=80, borrowings_cr=100)
    session_zero = _make_session(
        [
            _mapping_result([latest_zero, prior_zero]),
            _mapping_result([_fund_row()]),
        ]
    )
    result_zero = await compute_piotroski(uuid4(), session_zero)
    assert result_zero is not None
    assert result_zero.detail.f6_liquidity_improving is False

    # Case 3: borrowings=0 in prior → F6=False
    latest_nz = _hist_row(cfo_cr=120, borrowings_cr=100)
    prior_nz = _hist_row(cfo_cr=80, borrowings_cr=0)
    session_nz = _make_session(
        [
            _mapping_result([latest_nz, prior_nz]),
            _mapping_result([_fund_row()]),
        ]
    )
    result_nz = await compute_piotroski(uuid4(), session_nz)
    assert result_nz is not None
    assert result_nz.detail.f6_liquidity_improving is False


@pytest.mark.asyncio
async def test_piotroski_f7_no_dilution_check() -> None:
    """current equity_capital=100, prior=110 → F7=True (not increased).
    current=110, prior=100 → F7=False (diluted).
    """
    # Case 1: no dilution
    latest_nodil = _hist_row(equity_capital_cr=100)
    prior_nodil = _hist_row(equity_capital_cr=110)
    session_nodil = _make_session(
        [
            _mapping_result([latest_nodil, prior_nodil]),
            _mapping_result([_fund_row()]),
        ]
    )
    result_nodil = await compute_piotroski(uuid4(), session_nodil)
    assert result_nodil is not None
    assert result_nodil.detail.f7_no_dilution is True

    # Case 2: diluted
    latest_dil = _hist_row(equity_capital_cr=110)
    prior_dil = _hist_row(equity_capital_cr=100)
    session_dil = _make_session(
        [
            _mapping_result([latest_dil, prior_dil]),
            _mapping_result([_fund_row()]),
        ]
    )
    result_dil = await compute_piotroski(uuid4(), session_dil)
    assert result_dil is not None
    assert result_dil.detail.f7_no_dilution is False


@pytest.mark.asyncio
async def test_piotroski_f8_margin_expanding() -> None:
    """current opm=15, prior=12 → F8=True; current=10, prior=12 → F8=False."""
    # Case 1: expanding
    latest_exp = _hist_row(opm_pct=15)
    prior_exp = _hist_row(opm_pct=12)
    session_exp = _make_session(
        [
            _mapping_result([latest_exp, prior_exp]),
            _mapping_result([_fund_row()]),
        ]
    )
    result_exp = await compute_piotroski(uuid4(), session_exp)
    assert result_exp is not None
    assert result_exp.detail.f8_margin_expanding is True

    # Case 2: contracting
    latest_con = _hist_row(opm_pct=10)
    prior_con = _hist_row(opm_pct=12)
    session_con = _make_session(
        [
            _mapping_result([latest_con, prior_con]),
            _mapping_result([_fund_row()]),
        ]
    )
    result_con = await compute_piotroski(uuid4(), session_con)
    assert result_con is not None
    assert result_con.detail.f8_margin_expanding is False


@pytest.mark.asyncio
async def test_piotroski_f9_asset_turnover_improving() -> None:
    """curr rev=1000/assets=500 (=2.0) > prior rev=800/assets=500 (=1.6) → F9=True.
    prior rev=1200/assets=500 (=2.4) > curr → F9=False.
    """
    # Case 1: improving
    latest_imp = _hist_row(revenue_cr=1000, total_assets_cr=500)
    prior_imp = _hist_row(revenue_cr=800, total_assets_cr=500)
    session_imp = _make_session(
        [
            _mapping_result([latest_imp, prior_imp]),
            _mapping_result([_fund_row()]),
        ]
    )
    result_imp = await compute_piotroski(uuid4(), session_imp)
    assert result_imp is not None
    assert result_imp.detail.f9_asset_turnover_improving is True

    # Case 2: declining
    latest_dec = _hist_row(revenue_cr=1000, total_assets_cr=500)
    prior_dec = _hist_row(revenue_cr=1200, total_assets_cr=500)
    session_dec = _make_session(
        [
            _mapping_result([latest_dec, prior_dec]),
            _mapping_result([_fund_row()]),
        ]
    )
    result_dec = await compute_piotroski(uuid4(), session_dec)
    assert result_dec is not None
    assert result_dec.detail.f9_asset_turnover_improving is False


@pytest.mark.asyncio
async def test_piotroski_grade_thresholds_all_four_bands() -> None:
    """Force various scores to verify all four grade bands.

    Score 0,2 → WEAK; 3,5 → NEUTRAL; 6,7 → GOOD; 8,9 → STRONG.
    """
    from backend.services.derived_signals import _grade

    assert _grade(0) == "WEAK"
    assert _grade(2) == "WEAK"
    assert _grade(3) == "NEUTRAL"
    assert _grade(5) == "NEUTRAL"
    assert _grade(6) == "GOOD"
    assert _grade(7) == "GOOD"
    assert _grade(8) == "STRONG"
    assert _grade(9) == "STRONG"


@pytest.mark.asyncio
async def test_piotroski_sql_uses_period_type_annual() -> None:
    """Verify the history SQL includes period_type = 'annual'."""
    from backend.services.derived_signals import _PIOTROSKI_HISTORY_SQL

    sql_text = str(_PIOTROSKI_HISTORY_SQL)
    assert "annual" in sql_text, "Piotroski history SQL must filter period_type = 'annual'"
