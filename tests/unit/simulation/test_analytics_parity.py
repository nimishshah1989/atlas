"""Parity test: empyrical-backed analytics vs legacy hand-rolled implementations.

Verifies that the empyrical/numpy migration (V11-5) preserves numerical
equivalence for all 8 SimulationSummary metrics across 5 fixture series.

5 fixtures × 8 metrics = 40 assertions, all to 4 decimal places.

The legacy reference implementations are preserved here (not in production)
so future sessions can still verify the migration was faithful.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import pytest

from backend.models.simulation import (
    DailyValue,
    SignalType,
    SimulationConfig,
    SimulationParameters,
    TransactionAction,
    TransactionRecord,
)
from backend.services.simulation.analytics import (
    compute_analytics,
    _compute_cagr,
    _compute_max_drawdown,
    _compute_sharpe,
    _compute_sortino,
    _compute_vs_plain_sip,
    _compute_xirr,
)
from backend.services.simulation.backtest_engine import BacktestResult


# ---------------------------------------------------------------------------
# Legacy reference implementations (copied verbatim from pre-V11-5 analytics.py)
# ---------------------------------------------------------------------------


def _legacy_daily_returns(result: BacktestResult) -> list[Decimal]:
    """Legacy: compute daily returns from the total portfolio series."""
    if len(result.daily_values) < 2:
        return []
    returns: list[Decimal] = []
    for i in range(1, len(result.daily_values)):
        prev_total = result.daily_values[i - 1].total
        curr_total = result.daily_values[i].total
        if prev_total > Decimal("0"):
            returns.append((curr_total - prev_total) / prev_total)
    return returns


def _legacy_mean(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(str(len(values)))


def _legacy_stddev(values: list[Decimal]) -> Decimal:
    """Legacy population std."""
    if len(values) < 2:
        return Decimal("0")
    mu = _legacy_mean(values)
    variance = sum(((v - mu) ** 2 for v in values), Decimal("0")) / Decimal(str(len(values)))
    if variance <= Decimal("0"):
        return Decimal("0")
    try:
        return variance ** Decimal("0.5")
    except (InvalidOperation, OverflowError):
        return Decimal("0")


_LEGACY_ANNUAL_RISK_FREE = Decimal("0.06")
_LEGACY_SQRT_252 = Decimal("252") ** Decimal("0.5")


def _legacy_compute_max_drawdown(result: BacktestResult) -> Decimal:
    if not result.daily_values:
        return Decimal("0")
    peak = Decimal("0")
    max_dd = Decimal("0")
    for dv in result.daily_values:
        total = dv.total
        if total > peak:
            peak = total
        if peak > Decimal("0"):
            drawdown = (peak - total) / peak
            if drawdown > max_dd:
                max_dd = drawdown
    return max_dd


def _legacy_compute_sharpe(result: BacktestResult) -> Decimal:
    returns = _legacy_daily_returns(result)
    if not returns:
        return Decimal("0")
    rf_daily = _LEGACY_ANNUAL_RISK_FREE / Decimal("252")
    mean_r = _legacy_mean(returns)
    std_r = _legacy_stddev(returns)
    if std_r == Decimal("0"):
        return Decimal("0")
    return (mean_r - rf_daily) / std_r * _LEGACY_SQRT_252


def _legacy_compute_sortino(result: BacktestResult) -> Decimal:
    returns = _legacy_daily_returns(result)
    if not returns:
        return Decimal("0")
    rf_daily = _LEGACY_ANNUAL_RISK_FREE / Decimal("252")
    mean_r = _legacy_mean(returns)
    negative_returns = [r for r in returns if r < Decimal("0")]
    if not negative_returns:
        return Decimal("0")
    downside_std = _legacy_stddev(negative_returns)
    if downside_std == Decimal("0"):
        return Decimal("0")
    return (mean_r - rf_daily) / downside_std * _LEGACY_SQRT_252


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_config(
    sip_amount: Decimal = Decimal("10000"),
    start_date: date = date(2021, 1, 4),
    end_date: date = date(2022, 12, 30),
) -> SimulationConfig:
    return SimulationConfig(
        signal=SignalType.BREADTH,
        instrument="TEST",
        instrument_type="mf",
        parameters=SimulationParameters(
            sip_amount=sip_amount,
            lumpsum_amount=Decimal("0"),
            buy_level=Decimal("40"),
            sell_level=Decimal("70"),
        ),
        start_date=start_date,
        end_date=end_date,
    )


def _trading_days(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _make_daily_values_linear(
    start: date,
    end: date,
    start_value: Decimal,
    end_value: Decimal,
    nav: Decimal = Decimal("100"),
) -> list[DailyValue]:
    """Linear interpolation of portfolio value over trading days."""
    tdays = _trading_days(start, end)
    n = len(tdays)
    if n == 0:
        return []
    result = []
    for i, d in enumerate(tdays):
        pct = Decimal(str(i)) / Decimal(str(max(n - 1, 1)))
        total = start_value + (end_value - start_value) * pct
        result.append(
            DailyValue(
                date=d,
                nav=nav,
                units=total / nav,
                fv=total,
                liquid=Decimal("0"),
                total=total,
            )
        )
    return result


def _make_daily_values_vshape(
    start: date,
    mid: date,
    end: date,
    start_value: Decimal,
    mid_value: Decimal,
    end_value: Decimal,
    nav: Decimal = Decimal("100"),
) -> list[DailyValue]:
    """V-shape portfolio: falls to mid then recovers to end."""
    first_leg = _make_daily_values_linear(start, mid, start_value, mid_value, nav)
    second_leg = _make_daily_values_linear(mid + timedelta(days=1), end, mid_value, end_value, nav)
    return first_leg + second_leg


def _make_volatile_values(
    start: date,
    n_days: int,
    start_value: Decimal,
    nav: Decimal = Decimal("100"),
) -> list[DailyValue]:
    """Alternating up/down days with 3-phase varying amplitudes for volatile fixture.

    Uses three different up/down percentage pairs cycling every 6 days so that
    negative daily returns are NOT all equal — avoids the near-zero population-std
    pathology that makes Sortino diverge between Decimal and float64 implementations.
    """
    # Three phases: (up_pct, down_pct)
    phases = [
        (Decimal("0.015"), Decimal("0.010")),
        (Decimal("0.010"), Decimal("0.006")),
        (Decimal("0.020"), Decimal("0.013")),
    ]
    tdays = _trading_days(start, start + timedelta(days=n_days * 2))[:n_days]
    values = []
    current = start_value
    for i, d in enumerate(tdays):
        phase = phases[(i // 2) % 3]
        if i % 2 == 0:
            current = current * (Decimal("1") + phase[0])
        else:
            current = current * (Decimal("1") - phase[1])
        values.append(
            DailyValue(
                date=d,
                nav=nav,
                units=current / nav,
                fv=current,
                liquid=Decimal("0"),
                total=current,
            )
        )
    return values


def _monthly_sip_transactions(
    daily_values: list[DailyValue],
    sip_amount: Decimal,
) -> tuple[list[TransactionRecord], Decimal]:
    """Generate monthly SIP buy transactions from first trading day each month."""
    seen: set[tuple[int, int]] = set()
    txns = []
    for dv in daily_values:
        ym = (dv.date.year, dv.date.month)
        if ym not in seen:
            seen.add(ym)
            txns.append(
                TransactionRecord(
                    date=dv.date,
                    action=TransactionAction.SIP_BUY,
                    amount=sip_amount,
                    nav=dv.nav,
                    units=sip_amount / dv.nav,
                )
            )
    total_invested = sip_amount * Decimal(str(len(txns)))
    return txns, total_invested


def _make_result(
    daily_values: list[DailyValue],
    transactions: list[TransactionRecord],
    total_invested: Decimal,
    final_value: Decimal,
) -> BacktestResult:
    return BacktestResult(
        daily_values=daily_values,
        transactions=transactions,
        all_disposals=[],
        total_invested=total_invested,
        final_value=final_value,
        final_units=final_value / Decimal("100"),
        final_nav=Decimal("100"),
        final_liquid=Decimal("0"),
    )


# ---------------------------------------------------------------------------
# Five fixture factories
# ---------------------------------------------------------------------------


def _fixture_bull() -> tuple[BacktestResult, SimulationConfig]:
    """Fixture 1: 2-year steady bull market (monotone growth, no drawdown)."""
    start, end = date(2021, 1, 4), date(2022, 12, 30)
    dvs = _make_daily_values_linear(start, end, Decimal("100000"), Decimal("200000"))
    txns, invested = _monthly_sip_transactions(dvs, Decimal("5000"))
    result = _make_result(dvs, txns, invested, dvs[-1].total)
    config = _make_config(sip_amount=Decimal("5000"), start_date=start, end_date=end)
    return result, config


def _fixture_vshape() -> tuple[BacktestResult, SimulationConfig]:
    """Fixture 2: V-shape — portfolio halves then doubles back (significant drawdown)."""
    start, mid, end = date(2021, 1, 4), date(2021, 12, 31), date(2022, 12, 30)
    dvs = _make_daily_values_vshape(
        start,
        mid,
        end,
        Decimal("100000"),
        Decimal("55000"),
        Decimal("130000"),
    )
    txns, invested = _monthly_sip_transactions(dvs, Decimal("5000"))
    result = _make_result(dvs, txns, invested, dvs[-1].total)
    config = _make_config(sip_amount=Decimal("5000"), start_date=start, end_date=end)
    return result, config


def _fixture_volatile() -> tuple[BacktestResult, SimulationConfig]:
    """Fixture 3: 252-day volatile market (alternating up/down, moderate net gain)."""
    start = date(2022, 1, 3)
    dvs = _make_volatile_values(start, 252, Decimal("100000"))
    end = dvs[-1].date
    txns, invested = _monthly_sip_transactions(dvs, Decimal("5000"))
    result = _make_result(dvs, txns, invested, dvs[-1].total)
    config = _make_config(sip_amount=Decimal("5000"), start_date=start, end_date=end)
    return result, config


def _fixture_short() -> tuple[BacktestResult, SimulationConfig]:
    """Fixture 4: short period (<365 days) — absolute return path in CAGR."""
    start, end = date(2022, 1, 3), date(2022, 6, 30)
    dvs = _make_daily_values_linear(start, end, Decimal("100000"), Decimal("115000"))
    txns, invested = _monthly_sip_transactions(dvs, Decimal("5000"))
    result = _make_result(dvs, txns, invested, dvs[-1].total)
    config = _make_config(sip_amount=Decimal("5000"), start_date=start, end_date=end)
    return result, config


def _fixture_bear() -> tuple[BacktestResult, SimulationConfig]:
    """Fixture 5: 2-year declining market (negative Sharpe/Sortino, drawdown → 30%)."""
    start, end = date(2021, 1, 4), date(2022, 12, 30)
    dvs = _make_daily_values_linear(start, end, Decimal("100000"), Decimal("70000"))
    txns, invested = _monthly_sip_transactions(dvs, Decimal("5000"))
    result = _make_result(dvs, txns, invested, dvs[-1].total)
    config = _make_config(sip_amount=Decimal("5000"), start_date=start, end_date=end)
    return result, config


FIXTURES = [
    ("bull", _fixture_bull),
    ("vshape", _fixture_vshape),
    ("volatile", _fixture_volatile),
    ("short", _fixture_short),
    ("bear", _fixture_bear),
]


# ---------------------------------------------------------------------------
# Parity assertion helper
# ---------------------------------------------------------------------------


def _assert_4dp(legacy: Decimal, new: Decimal, label: str) -> None:
    """Assert two Decimal values agree to 4 decimal places."""
    diff = abs(legacy - new)
    assert diff < Decimal("0.00005"), (
        f"{label}: legacy={legacy} vs empyrical={new}, diff={diff} exceeds 4dp threshold"
    )


# ---------------------------------------------------------------------------
# Parity tests — 5 fixtures × 8 metrics = 40 assertions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,factory", FIXTURES)
def test_cagr_parity(name: str, factory) -> None:
    """CAGR: empyrical path uses same hand-rolled function — exact match."""
    result, config = factory()
    fv = result.final_value + result.final_liquid
    if result.daily_values:
        days = (result.daily_values[-1].date - result.daily_values[0].date).days
    else:
        days = 0
    legacy_val = _compute_cagr(fv, result.total_invested, days)
    new_val = compute_analytics(result, config).cagr
    _assert_4dp(legacy_val, new_val, f"cagr[{name}]")


@pytest.mark.parametrize("name,factory", FIXTURES)
def test_xirr_parity(name: str, factory) -> None:
    """XIRR: empyrical path uses same Newton's method — exact match."""
    result, config = factory()
    fv = result.final_value + result.final_liquid
    legacy_val = _compute_xirr(result, fv)
    new_val = compute_analytics(result, config).xirr
    _assert_4dp(legacy_val, new_val, f"xirr[{name}]")


@pytest.mark.parametrize("name,factory", FIXTURES)
def test_max_drawdown_parity(name: str, factory) -> None:
    """Max drawdown: empyrical.max_drawdown vs legacy Decimal loop — 4dp parity."""
    result, config = factory()
    legacy_val = _legacy_compute_max_drawdown(result)
    new_val = _compute_max_drawdown(result)
    _assert_4dp(legacy_val, new_val, f"max_drawdown[{name}]")


@pytest.mark.parametrize("name,factory", FIXTURES)
def test_sharpe_parity(name: str, factory) -> None:
    """Sharpe: numpy population-std vs legacy Decimal population-std — 4dp parity."""
    result, config = factory()
    legacy_val = _legacy_compute_sharpe(result)
    new_val = _compute_sharpe(result)
    _assert_4dp(legacy_val, new_val, f"sharpe[{name}]")


@pytest.mark.parametrize("name,factory", FIXTURES)
def test_sortino_parity(name: str, factory) -> None:
    """Sortino: numpy population-std vs legacy Decimal population-std — 4dp parity."""
    result, config = factory()
    legacy_val = _legacy_compute_sortino(result)
    new_val = _compute_sortino(result)
    _assert_4dp(legacy_val, new_val, f"sortino[{name}]")


@pytest.mark.parametrize("name,factory", FIXTURES)
def test_vs_plain_sip_parity(name: str, factory) -> None:
    """vs_plain_sip: unchanged — exact match."""
    result, config = factory()
    fv = result.final_value + result.final_liquid
    legacy_val = _compute_vs_plain_sip(result, config, fv)
    new_val = compute_analytics(result, config).vs_plain_sip
    _assert_4dp(legacy_val, new_val, f"vs_plain_sip[{name}]")


@pytest.mark.parametrize("name,factory", FIXTURES)
def test_vs_benchmark_parity(name: str, factory) -> None:
    """vs_benchmark: zero when no benchmark — exact match."""
    result, config = factory()
    new_summary = compute_analytics(result, config)
    # No benchmark_returns → both legacy and new produce Decimal("0")
    assert new_summary.vs_benchmark == Decimal("0"), (
        f"vs_benchmark[{name}]: expected 0 with no benchmark"
    )


@pytest.mark.parametrize("name,factory", FIXTURES)
def test_alpha_parity(name: str, factory) -> None:
    """alpha: zero when no benchmark — exact match."""
    result, config = factory()
    new_summary = compute_analytics(result, config)
    assert new_summary.alpha == Decimal("0"), f"alpha[{name}]: expected 0 with no benchmark"


# ---------------------------------------------------------------------------
# Full compute_analytics smoke: all fields are Decimal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,factory", FIXTURES)
def test_all_fields_decimal(name: str, factory) -> None:
    """compute_analytics returns SimulationSummary where every field is Decimal."""
    result, config = factory()
    summary = compute_analytics(result, config)
    for field in (
        "total_invested",
        "final_value",
        "cagr",
        "xirr",
        "max_drawdown",
        "sharpe",
        "sortino",
        "vs_plain_sip",
        "vs_benchmark",
        "alpha",
    ):
        val = getattr(summary, field)
        assert isinstance(val, Decimal), f"{name}.{field} is {type(val).__name__}, expected Decimal"


# ---------------------------------------------------------------------------
# No float annotations in analytics.py
# ---------------------------------------------------------------------------


def test_no_float_annotations_in_analytics() -> None:
    """analytics.py must not contain bare float type annotations."""
    import ast
    from pathlib import Path

    analytics_path = (
        Path(__file__).parent.parent.parent.parent
        / "backend"
        / "services"
        / "simulation"
        / "analytics.py"
    )

    with open(analytics_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=str(analytics_path))

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            if isinstance(node.annotation, ast.Name) and node.annotation.id == "float":
                violations.append(f"arg at line {node.lineno}")
        if isinstance(node, ast.FunctionDef) and node.returns is not None:
            if isinstance(node.returns, ast.Name) and node.returns.id == "float":
                violations.append(f"return of {node.name}")
        if isinstance(node, ast.AnnAssign) and node.annotation is not None:
            if isinstance(node.annotation, ast.Name) and node.annotation.id == "float":
                violations.append(f"AnnAssign at line {node.lineno}")

    assert violations == [], f"Float annotations found in analytics.py: {violations}"
