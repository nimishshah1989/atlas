"""Analytics module — pure computation of summary statistics from BacktestResult.

No DB, no I/O, no async. All arithmetic in Decimal — NEVER float.

Metrics computed:
  CAGR, XIRR, max_drawdown, Sharpe, Sortino, vs_plain_sip, vs_benchmark, alpha
"""

from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from backend.models.simulation import SimulationConfig, SimulationSummary
from backend.services.simulation.backtest_engine import BacktestResult


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_analytics(
    result: BacktestResult,
    config: SimulationConfig,
    benchmark_returns: Optional[list[tuple[date, Decimal]]] = None,
) -> SimulationSummary:
    """Compute summary analytics from a BacktestResult.

    Args:
        result: Raw backtest output.
        config: The simulation config (for SIP amount, date range, etc.).
        benchmark_returns: Optional list of (date, price) for benchmark comparison.

    Returns:
        SimulationSummary with all analytics fields populated as Decimal.
    """
    total_invested = result.total_invested
    final_value = result.final_value + result.final_liquid

    # Guard against zero investment
    if total_invested == Decimal("0"):
        return _zero_summary(total_invested, final_value)

    # Date range
    if result.daily_values:
        first_date = result.daily_values[0].date
        last_date = result.daily_values[-1].date
        days = (last_date - first_date).days
    else:
        days = 0

    # CAGR / absolute return
    cagr = _compute_cagr(final_value, total_invested, days)

    # XIRR from cashflow series
    xirr = _compute_xirr(result, final_value)

    # Risk metrics from daily total series
    max_drawdown = _compute_max_drawdown(result)
    sharpe = _compute_sharpe(result)
    sortino = _compute_sortino(result)

    # vs plain SIP
    vs_plain_sip = _compute_vs_plain_sip(result, config, final_value)

    # vs benchmark and alpha
    if benchmark_returns is not None and len(benchmark_returns) >= 2:
        vs_benchmark, alpha = _compute_vs_benchmark(cagr, benchmark_returns, days)
    else:
        vs_benchmark = Decimal("0")
        alpha = Decimal("0")

    return SimulationSummary(
        total_invested=total_invested,
        final_value=final_value,
        xirr=xirr,
        cagr=cagr,
        vs_plain_sip=vs_plain_sip,
        vs_benchmark=vs_benchmark,
        alpha=alpha,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        sortino=sortino,
    )


# ---------------------------------------------------------------------------
# CAGR
# ---------------------------------------------------------------------------


def _compute_cagr(
    final_value: Decimal,
    total_invested: Decimal,
    days: int,
) -> Decimal:
    """Compute CAGR or absolute return.

    If period <= 365 days: absolute return = (final - invested) / invested.
    If period > 365 days: annualized CAGR using Decimal power.
    """
    if total_invested == Decimal("0"):
        return Decimal("0")

    ratio = final_value / total_invested

    if days <= 365:
        return ratio - Decimal("1")

    if ratio <= Decimal("0"):
        return Decimal("0")

    try:
        exponent = Decimal("365.25") / Decimal(str(days))
        # Decimal supports ** with Decimal exponents natively
        cagr = ratio**exponent - Decimal("1")
        return cagr
    except (InvalidOperation, ZeroDivisionError, OverflowError):
        return Decimal("0")


# ---------------------------------------------------------------------------
# XIRR — Newton's method
# ---------------------------------------------------------------------------


def _compute_xirr(result: BacktestResult, final_value: Decimal) -> Decimal:
    """Compute XIRR using Newton's method on the cashflow series.

    Cashflows: each buy is negative (outflow), terminal value is positive.
    Uses dates from transactions + a terminal cashflow at last date.
    All arithmetic is pure Decimal — no float conversions.
    """
    if not result.transactions:
        return Decimal("0")

    # Build cashflow list: (date, amount) where buys are negative
    cashflows: list[tuple[date, Decimal]] = []

    from backend.models.simulation import TransactionAction

    for tx in result.transactions:
        if tx.action in (TransactionAction.SIP_BUY, TransactionAction.LUMPSUM_BUY):
            cashflows.append((tx.date, -tx.amount))
        # REDEPLOY is not an external cashflow (money stays in the system)

    if not cashflows:
        return Decimal("0")

    # Terminal cashflow
    last_date = result.daily_values[-1].date if result.daily_values else cashflows[-1][0]
    cashflows.append((last_date, final_value))

    # Use the first cashflow date as reference
    ref_date = cashflows[0][0]

    def _years(cf_date: date) -> Decimal:
        """Days difference as Decimal years."""
        return Decimal(str((cf_date - ref_date).days)) / Decimal("365.25")

    def npv(rate: Decimal) -> Decimal:
        total = Decimal("0")
        base = Decimal("1") + rate
        if base <= Decimal("0"):
            return Decimal("0")
        for cf_date, amount in cashflows:
            yr = _years(cf_date)
            try:
                factor = base**yr
                if factor == Decimal("0"):
                    return Decimal("0")
                total += amount / factor
            except (InvalidOperation, ZeroDivisionError, OverflowError):
                return Decimal("0")
        return total

    def npv_derivative(rate: Decimal) -> Decimal:
        total = Decimal("0")
        base = Decimal("1") + rate
        if base <= Decimal("0"):
            return Decimal("0")
        for cf_date, amount in cashflows:
            yr = _years(cf_date)
            try:
                factor = base ** (yr + Decimal("1"))
                if factor == Decimal("0"):
                    continue
                total -= amount * yr / factor
            except (InvalidOperation, ZeroDivisionError, OverflowError):
                continue
        return total

    # Newton's method — 20 iterations
    rate = Decimal("0.10")  # Initial guess: 10%
    tolerance = Decimal("0.0001")

    for _ in range(20):
        try:
            f_val = npv(rate)
            f_deriv = npv_derivative(rate)
            if f_deriv == Decimal("0"):
                break
            new_rate = rate - f_val / f_deriv
            if abs(new_rate - rate) < tolerance:
                rate = new_rate
                break
            rate = new_rate
        except (InvalidOperation, ZeroDivisionError, OverflowError):
            return Decimal("0")

    # Sanity check: XIRR must be within reasonable bounds
    if rate < Decimal("-0.999") or rate > Decimal("100"):
        return Decimal("0")

    return rate


# ---------------------------------------------------------------------------
# Max Drawdown
# ---------------------------------------------------------------------------


def _compute_max_drawdown(result: BacktestResult) -> Decimal:
    """Compute maximum drawdown from the daily total portfolio series.

    max_drawdown = max((peak - trough) / peak) over all (peak, subsequent_trough) pairs.
    Returns a positive Decimal representing the magnitude (e.g. 0.30 for 30% drawdown).
    """
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


# ---------------------------------------------------------------------------
# Daily returns helper
# ---------------------------------------------------------------------------


def _daily_returns(result: BacktestResult) -> list[Decimal]:
    """Compute daily returns from the total portfolio series."""
    if len(result.daily_values) < 2:
        return []

    returns: list[Decimal] = []
    for i in range(1, len(result.daily_values)):
        prev_total = result.daily_values[i - 1].total
        curr_total = result.daily_values[i].total
        if prev_total > Decimal("0"):
            returns.append((curr_total - prev_total) / prev_total)

    return returns


def _mean(values: list[Decimal]) -> Decimal:
    """Compute arithmetic mean of a list of Decimals."""
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(str(len(values)))


def _stddev(values: list[Decimal]) -> Decimal:
    """Compute population standard deviation of a list of Decimals.

    Uses Decimal ** Decimal("0.5") for square root.
    """
    if len(values) < 2:
        return Decimal("0")
    mu = _mean(values)
    variance = sum(((v - mu) ** 2 for v in values), Decimal("0")) / Decimal(str(len(values)))
    if variance <= Decimal("0"):
        return Decimal("0")
    try:
        return variance ** Decimal("0.5")
    except (InvalidOperation, OverflowError):
        return Decimal("0")


# ---------------------------------------------------------------------------
# Sharpe Ratio
# ---------------------------------------------------------------------------

_ANNUAL_RISK_FREE = Decimal("0.06")  # India ~6% annual
_SQRT_252 = Decimal("252") ** Decimal("0.5")  # Pre-computed once at module level


def _compute_sharpe(result: BacktestResult) -> Decimal:
    """Sharpe ratio: (mean_daily_return - rf_daily) / stddev * sqrt(252)."""
    returns = _daily_returns(result)
    if not returns:
        return Decimal("0")

    rf_daily = _ANNUAL_RISK_FREE / Decimal("252")
    mean_r = _mean(returns)
    std_r = _stddev(returns)

    if std_r == Decimal("0"):
        return Decimal("0")

    return (mean_r - rf_daily) / std_r * _SQRT_252


# ---------------------------------------------------------------------------
# Sortino Ratio
# ---------------------------------------------------------------------------


def _compute_sortino(result: BacktestResult) -> Decimal:
    """Sortino ratio: uses downside deviation (negative returns only)."""
    returns = _daily_returns(result)
    if not returns:
        return Decimal("0")

    rf_daily = _ANNUAL_RISK_FREE / Decimal("252")
    mean_r = _mean(returns)

    negative_returns = [r for r in returns if r < Decimal("0")]
    if not negative_returns:
        return Decimal("0")

    downside_std = _stddev(negative_returns)
    if downside_std == Decimal("0"):
        return Decimal("0")

    return (mean_r - rf_daily) / downside_std * _SQRT_252


# ---------------------------------------------------------------------------
# vs Plain SIP
# ---------------------------------------------------------------------------


def _compute_vs_plain_sip(
    result: BacktestResult,
    config: SimulationConfig,
    actual_final_value: Decimal,
) -> Decimal:
    """Compare actual strategy final value vs plain SIP final value.

    Plain SIP: same sip_amount every first trading day of each month,
    no signal timing, no lumpsum. Returns outperformance as Decimal ratio
    (e.g. 0.15 means 15% better than plain SIP).
    """
    if not result.daily_values:
        return Decimal("0")

    params = config.parameters
    sip_amount = params.sip_amount

    if sip_amount == Decimal("0"):
        return Decimal("0")

    # Reconstruct price map from daily_values
    price_map: dict[date, Decimal] = {dv.date: dv.nav for dv in result.daily_values}

    # Simulate plain SIP
    plain_units = Decimal("0")
    sip_months_done: set[tuple[int, int]] = set()

    for dv in result.daily_values:
        ym = (dv.date.year, dv.date.month)
        if ym not in sip_months_done:
            sip_months_done.add(ym)
            nav = price_map[dv.date]
            plain_units += sip_amount / nav

    last_nav = result.daily_values[-1].nav
    plain_final_value = plain_units * last_nav

    if plain_final_value == Decimal("0"):
        return Decimal("0")

    return (actual_final_value - plain_final_value) / plain_final_value


# ---------------------------------------------------------------------------
# vs Benchmark
# ---------------------------------------------------------------------------


def _compute_vs_benchmark(
    strategy_cagr: Decimal,
    benchmark_returns: list[tuple[date, Decimal]],
    days: int,
) -> tuple[Decimal, Decimal]:
    """Compute benchmark CAGR and alpha vs strategy.

    Returns (vs_benchmark, alpha) where both are Decimal.
    vs_benchmark: benchmark_cagr
    alpha: strategy_cagr - benchmark_cagr
    """
    if len(benchmark_returns) < 2:
        return Decimal("0"), Decimal("0")

    first_price = benchmark_returns[0][1]
    last_price = benchmark_returns[-1][1]

    if first_price == Decimal("0"):
        return Decimal("0"), Decimal("0")

    benchmark_cagr = _compute_cagr(last_price, first_price, days)
    alpha = strategy_cagr - benchmark_cagr

    return benchmark_cagr, alpha


# ---------------------------------------------------------------------------
# Zero summary helper
# ---------------------------------------------------------------------------


def _zero_summary(total_invested: Decimal, final_value: Decimal) -> SimulationSummary:
    return SimulationSummary(
        total_invested=total_invested,
        final_value=final_value,
        xirr=Decimal("0"),
        cagr=Decimal("0"),
        vs_plain_sip=Decimal("0"),
        vs_benchmark=Decimal("0"),
        alpha=Decimal("0"),
        max_drawdown=Decimal("0"),
        sharpe=Decimal("0"),
        sortino=Decimal("0"),
    )


# ---------------------------------------------------------------------------
# Utility: AST scan helpers (used in tests)
# ---------------------------------------------------------------------------


def _has_float_annotation(source_path: str) -> bool:
    """Return True if the source file contains any bare-float type annotation."""
    with open(source_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)

    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            ann = node.annotation
            if isinstance(ann, ast.Name) and ann.id == "float":
                return True
        if isinstance(node, ast.FunctionDef) and node.returns is not None:
            ret = node.returns
            if isinstance(ret, ast.Name) and ret.id == "float":
                return True
        if isinstance(node, ast.AnnAssign) and node.annotation is not None:
            ann = node.annotation
            if isinstance(ann, ast.Name) and ann.id == "float":
                return True

    return False


__all__ = [
    "compute_analytics",
    "_compute_cagr",
    "_compute_xirr",
    "_compute_max_drawdown",
    "_compute_sharpe",
    "_compute_sortino",
    "_compute_vs_plain_sip",
    "_compute_vs_benchmark",
    "_has_float_annotation",
]
