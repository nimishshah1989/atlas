"""Performance test: VectorbtBatchEngine 100-config sweep ≤1/10 of legacy.

Wall-clock test: 100 configs × same ~1000-day price/signal data.
  - Legacy path: 100 sequential BacktestEngine.run() calls.
  - Vectorbt path: 1 VectorbtBatchEngine.run_batch() call with all 100 configs.

Assertion: vbt_time <= legacy_time / SPEEDUP_FACTOR (SPEEDUP_FACTOR = 10).
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import Decimal

from backend.models.simulation import (
    SimulationConfig,
    SimulationParameters,
    SignalType,
)
from backend.services.simulation.backtest_engine import BacktestEngine
from backend.services.simulation.signal_adapters import (
    SignalPoint,
    SignalSeries,
    SignalState,
)
from backend.services.simulation.vectorbt_engine import VectorbtBatchEngine

SPEEDUP_FACTOR = 10  # vectorbt batch must be this much faster


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_long_price_series(
    start: date,
    end: date,
    price: Decimal = Decimal("100"),
) -> list[tuple[date, Decimal]]:
    """Daily Mon-Fri price series from start to end."""
    series = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            series.append((current, price))
        current += timedelta(days=1)
    return series


def _make_signal_series(
    price_series: list[tuple[date, Decimal]],
) -> SignalSeries:
    """HOLD signal for all dates — batch test uses SIP+BUY path only."""
    points = [
        SignalPoint(date=d, state=SignalState.HOLD, raw_value=Decimal("50"))
        for d, _ in price_series
    ]
    return SignalSeries(points=points, signal_type=SignalType.BREADTH)


def _make_config(
    sip_amount: Decimal,
    lumpsum_amount: Decimal = Decimal("0"),
    start_date: date = date(2020, 1, 2),
    end_date: date = date(2023, 12, 31),
) -> SimulationConfig:
    return SimulationConfig(
        signal=SignalType.BREADTH,
        instrument="TEST",
        instrument_type="mf",
        parameters=SimulationParameters(
            sip_amount=sip_amount,
            lumpsum_amount=lumpsum_amount,
            buy_level=Decimal("40"),
            sell_level=Decimal("70"),
            sell_pct=Decimal("100"),
            redeploy_pct=Decimal("100"),
            cooldown_days=30,
        ),
        start_date=start_date,
        end_date=end_date,
    )


# ---------------------------------------------------------------------------
# Performance test
# ---------------------------------------------------------------------------


def test_batch_100_configs_is_10x_faster_than_legacy() -> None:
    """100 configs in parallel must be ≤1/10 wall-clock vs 100 sequential legacy runs."""
    start_date = date(2020, 1, 2)
    end_date = date(2023, 12, 31)

    price_series = _make_long_price_series(start_date, end_date)
    signal_series = _make_signal_series(price_series)

    # 100 configs varying sip_amount from 1000 to 100000
    configs = [
        _make_config(
            sip_amount=Decimal(str(i * 1000)),
            lumpsum_amount=Decimal("0"),
            start_date=start_date,
            end_date=end_date,
        )
        for i in range(1, 101)
    ]

    # Legacy: 100 sequential runs
    t_start = time.perf_counter()
    for config in configs:
        BacktestEngine().run(config, price_series, signal_series)
    legacy_time = time.perf_counter() - t_start

    # Vectorbt batch: 100 configs simultaneously
    t_start = time.perf_counter()
    batch_results = VectorbtBatchEngine().run_batch(configs, price_series, signal_series)
    vbt_time = time.perf_counter() - t_start

    # Sanity check: batch returns correct number of results
    assert len(batch_results) == 100, f"Expected 100 results, got {len(batch_results)}"

    assert vbt_time <= legacy_time / SPEEDUP_FACTOR, (
        f"VectorbtBatchEngine not fast enough: "
        f"vbt={vbt_time:.3f}s vs legacy={legacy_time:.3f}s "
        f"(speedup={legacy_time / vbt_time:.1f}x, need {SPEEDUP_FACTOR}x)"
    )
