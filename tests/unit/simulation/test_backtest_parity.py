"""Parity tests: VectorbtEngine vs BacktestEngine.

5 reference scenarios × 12 output metrics = 60 assertions.
Each assertion: round(float(vbt_metric), 4) == round(float(legacy_metric), 4).

The 12 metrics:
  From BacktestResult:
    1. total_invested
    2. final_value
    3. final_units
    4. final_liquid
  From SimulationSummary (via compute_analytics):
    5.  cagr
    6.  xirr
    7.  vs_plain_sip
    8.  vs_benchmark
    9.  alpha
    10. max_drawdown
    11. sharpe
    12. sortino

The 5 scenarios:
  1. SIP-only (no signals, 6 months, 100-NAV)
  2. SIP + BUY signals, no SELL (3 months)
  3. SIP + BUY + SELL (100% sell), 4 months
  4. SIP + SELL (50%) + REENTRY, 4 months
  5. No SIP, lumpsum only (BUY signal at start), 6 months
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.models.simulation import (
    SimulationConfig,
    SimulationParameters,
    SignalType,
)
from backend.services.simulation.analytics import compute_analytics
from backend.services.simulation.backtest_engine import BacktestEngine
from backend.services.simulation.signal_adapters import (
    SignalPoint,
    SignalSeries,
    SignalState,
)
from backend.services.simulation.vectorbt_engine import VectorbtEngine


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_config(
    sip_amount: Decimal = Decimal("10000"),
    lumpsum_amount: Decimal = Decimal("50000"),
    buy_level: Decimal = Decimal("40"),
    sell_level: Decimal = Decimal("70"),
    reentry_level: Decimal | None = None,
    sell_pct: Decimal = Decimal("100"),
    redeploy_pct: Decimal = Decimal("100"),
    cooldown_days: int = 30,
    start_date: date = date(2023, 1, 2),
    end_date: date = date(2023, 6, 30),
) -> SimulationConfig:
    return SimulationConfig(
        signal=SignalType.BREADTH,
        instrument="TEST",
        instrument_type="mf",
        parameters=SimulationParameters(
            sip_amount=sip_amount,
            lumpsum_amount=lumpsum_amount,
            buy_level=buy_level,
            sell_level=sell_level,
            reentry_level=reentry_level,
            sell_pct=sell_pct,
            redeploy_pct=redeploy_pct,
            cooldown_days=cooldown_days,
        ),
        start_date=start_date,
        end_date=end_date,
    )


def _make_price_series(
    start: date,
    end: date,
    price: Decimal = Decimal("100"),
) -> list[tuple[date, Decimal]]:
    """Daily Mon-Fri price series with fixed price."""
    series = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            series.append((current, price))
        current += timedelta(days=1)
    return series


def _make_signal_series(
    price_series: list[tuple[date, Decimal]],
    state: SignalState = SignalState.HOLD,
) -> SignalSeries:
    """All-same-state signal series."""
    points = [SignalPoint(date=d, state=state, raw_value=Decimal("50")) for d, _ in price_series]
    return SignalSeries(points=points, signal_type=SignalType.BREADTH)


def _make_signal_series_on_date(
    price_series: list[tuple[date, Decimal]],
    signals: dict[date, SignalState],
    default: SignalState = SignalState.HOLD,
) -> SignalSeries:
    """Signal series with specific states on specific dates."""
    points = [
        SignalPoint(
            date=d,
            state=signals.get(d, default),
            raw_value=Decimal("50"),
        )
        for d, _ in price_series
    ]
    return SignalSeries(points=points, signal_type=SignalType.BREADTH)


# ---------------------------------------------------------------------------
# Core parity checker
# ---------------------------------------------------------------------------

_PARITY_METRICS = [
    "cagr",
    "xirr",
    "vs_plain_sip",
    "vs_benchmark",
    "alpha",
    "max_drawdown",
    "sharpe",
    "sortino",
]


def _check_parity(
    config: SimulationConfig,
    price_series: list[tuple[date, Decimal]],
    signal_series: SignalSeries,
    scenario_name: str,
) -> None:
    """Run both engines and assert 12 metrics agree to 4 decimal places."""
    legacy_result = BacktestEngine().run(config, price_series, signal_series)
    vbt_result = VectorbtEngine().run(config, price_series, signal_series)

    legacy_summary = compute_analytics(legacy_result, config)
    vbt_summary = compute_analytics(vbt_result, config)

    # 4 BacktestResult metrics
    result_checks = [
        ("total_invested", legacy_result.total_invested, vbt_result.total_invested),
        ("final_value", legacy_result.final_value, vbt_result.final_value),
        ("final_units", legacy_result.final_units, vbt_result.final_units),
        ("final_liquid", legacy_result.final_liquid, vbt_result.final_liquid),
    ]
    for metric_name, leg_val, vbt_val in result_checks:
        assert round(float(leg_val), 4) == round(float(vbt_val), 4), (
            f"[{scenario_name}] Mismatch on {metric_name}: legacy={leg_val} vs vectorbt={vbt_val}"
        )

    # 8 SimulationSummary metrics
    for metric_name in _PARITY_METRICS:
        leg_val = getattr(legacy_summary, metric_name)
        vbt_val = getattr(vbt_summary, metric_name)
        assert round(float(leg_val), 4) == round(float(vbt_val), 4), (
            f"[{scenario_name}] Mismatch on {metric_name}: legacy={leg_val} vs vectorbt={vbt_val}"
        )


# ---------------------------------------------------------------------------
# Scenario 1: SIP-only, no signals, 6 months, flat 100-NAV
# ---------------------------------------------------------------------------


def test_parity_scenario1_sip_only() -> None:
    """SIP-only, HOLD signals throughout — 6 months of flat NAV."""
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("0"),
        start_date=date(2023, 1, 2),
        end_date=date(2023, 6, 30),
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 6, 30))
    signal_series = _make_signal_series(price_series, SignalState.HOLD)

    _check_parity(config, price_series, signal_series, "SIP-only")


# ---------------------------------------------------------------------------
# Scenario 2: SIP + BUY signals, no SELL — 3 months
# ---------------------------------------------------------------------------


def test_parity_scenario2_sip_plus_buy() -> None:
    """SIP + BUY signals on specific dates, no SELL — 3 months."""
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("50000"),
        cooldown_days=0,
        start_date=date(2023, 1, 2),
        end_date=date(2023, 3, 31),
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 3, 31))
    # BUY signals on 3 dates
    buy_date_1 = date(2023, 1, 10)
    buy_date_2 = date(2023, 2, 8)
    buy_date_3 = date(2023, 3, 8)
    signal_series = _make_signal_series_on_date(
        price_series,
        {
            buy_date_1: SignalState.BUY,
            buy_date_2: SignalState.BUY,
            buy_date_3: SignalState.BUY,
        },
    )

    _check_parity(config, price_series, signal_series, "SIP+BUY")


# ---------------------------------------------------------------------------
# Scenario 3: SIP + BUY + SELL (100% sell) — 4 months
# ---------------------------------------------------------------------------


def test_parity_scenario3_sip_buy_sell() -> None:
    """SIP + BUY + 100% SELL — 4 months."""
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("50000"),
        sell_pct=Decimal("100"),
        cooldown_days=0,
        start_date=date(2022, 1, 3),
        end_date=date(2022, 4, 29),
    )
    price_series = _make_price_series(date(2022, 1, 3), date(2022, 4, 29))
    buy_date = date(2022, 1, 12)
    sell_date = date(2022, 3, 10)
    signal_series = _make_signal_series_on_date(
        price_series,
        {buy_date: SignalState.BUY, sell_date: SignalState.SELL},
    )

    _check_parity(config, price_series, signal_series, "SIP+BUY+SELL-100pct")


# ---------------------------------------------------------------------------
# Scenario 4: SIP + SELL (50%) + REENTRY — 4 months
# ---------------------------------------------------------------------------


def test_parity_scenario4_sell_partial_reentry() -> None:
    """SIP + 50% SELL + REENTRY — 4 months."""
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("0"),
        sell_pct=Decimal("50"),
        redeploy_pct=Decimal("100"),
        reentry_level=Decimal("45"),
        start_date=date(2023, 1, 2),
        end_date=date(2023, 4, 28),
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 4, 28))
    sell_date = date(2023, 2, 8)
    reentry_date = date(2023, 2, 22)
    signal_series = _make_signal_series_on_date(
        price_series,
        {sell_date: SignalState.SELL, reentry_date: SignalState.REENTRY},
    )

    _check_parity(config, price_series, signal_series, "SIP+SELL-50pct+REENTRY")


# ---------------------------------------------------------------------------
# Scenario 5: No SIP, lumpsum-only at BUY signal start — 6 months
# ---------------------------------------------------------------------------


def test_parity_scenario5_lumpsum_only() -> None:
    """No SIP, lumpsum only on first BUY signal — 6 months."""
    config = _make_config(
        sip_amount=Decimal("0"),
        lumpsum_amount=Decimal("100000"),
        cooldown_days=30,
        start_date=date(2023, 1, 2),
        end_date=date(2023, 6, 30),
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 6, 30))
    buy_date = date(2023, 1, 10)
    signal_series = _make_signal_series_on_date(
        price_series,
        {buy_date: SignalState.BUY},
    )

    _check_parity(config, price_series, signal_series, "lumpsum-only")
