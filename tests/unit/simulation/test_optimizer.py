"""Unit tests for the Parameter Optimizer — V3-6.

Tests cover:
- ParameterRange validation
- run_optimization() with small fixture data (10-20 trials, fast)
- Each objective metric (xirr, sharpe, cagr, sortino)
- Results within specified ranges
- All values are Decimal at boundary (not float)
- Edge case: all trials fail → graceful result
- AST scan: no float annotations, no print() calls
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.models.simulation import (
    SimulationConfig,
    SimulationParameters,
    SignalType,
)
from backend.services.simulation.optimizer import (
    ParameterRange,
    OptimizerResult,
    TrialRecord,
    run_optimization,
    _has_float_annotation,
    _has_print_call,
)
from backend.services.simulation.signal_adapters import (
    SignalPoint,
    SignalSeries,
    SignalState,
)

# ---------------------------------------------------------------------------
# Paths for AST scans
# ---------------------------------------------------------------------------

OPTIMIZER_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "backend"
    / "services"
    / "simulation"
    / "optimizer.py"
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_config(
    buy_level: Decimal = Decimal("30"),
    sell_level: Decimal = Decimal("70"),
    sip_amount: Decimal = Decimal("10000"),
    lumpsum_amount: Decimal = Decimal("50000"),
    cooldown_days: int = 30,
    start_date: date = date(2023, 1, 2),
    end_date: date = date(2023, 6, 30),
) -> SimulationConfig:
    return SimulationConfig(
        signal=SignalType.BREADTH,
        instrument="TEST_MF",
        instrument_type="mf",
        parameters=SimulationParameters(
            sip_amount=sip_amount,
            lumpsum_amount=lumpsum_amount,
            buy_level=buy_level,
            sell_level=sell_level,
            sell_pct=Decimal("100"),
            redeploy_pct=Decimal("100"),
            cooldown_days=cooldown_days,
        ),
        start_date=start_date,
        end_date=end_date,
    )


def _make_price_series(
    start: date = date(2023, 1, 2),
    end: date = date(2023, 6, 30),
    base_price: Decimal = Decimal("100"),
) -> list[tuple[date, Decimal]]:
    """Generate Mon-Fri price series with slight upward drift."""
    series = []
    current = start
    day_num = 0
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            # Small drift so CAGR/XIRR are non-trivial
            price = base_price + Decimal(str(day_num)) * Decimal("0.1")
            series.append((current, price))
            day_num += 1
        current += timedelta(days=1)
    return series


def _make_signal_series(
    start: date = date(2023, 1, 2),
    end: date = date(2023, 6, 30),
) -> SignalSeries:
    """Build a SignalSeries with a BUY on first trading day of each month, HOLD otherwise."""
    points = []
    current = start
    prev_month = -1
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            # BUY on first trading day of each new month
            if current.month != prev_month:
                state = SignalState.BUY
                prev_month = current.month
            else:
                state = SignalState.HOLD
            points.append(
                SignalPoint(
                    date=current,
                    state=state,
                    raw_value=Decimal("35") if state == SignalState.BUY else Decimal("50"),
                )
            )
        current += timedelta(days=1)
    return SignalSeries(points=points)


# ---------------------------------------------------------------------------
# Tests: ParameterRange validation
# ---------------------------------------------------------------------------


def test_parameter_range_basic() -> None:
    """ParameterRange stores min/max as Decimal."""
    pr = ParameterRange(min_val=Decimal("20"), max_val=Decimal("50"))
    assert pr.min_val == Decimal("20")
    assert pr.max_val == Decimal("50")
    assert pr.step is None


def test_parameter_range_with_step() -> None:
    """ParameterRange with step stores step as Decimal."""
    pr = ParameterRange(min_val=Decimal("10"), max_val=Decimal("100"), step=Decimal("10"))
    assert pr.step == Decimal("10")


def test_parameter_range_coerces_int_inputs() -> None:
    """ParameterRange coerces int min_val/max_val to Decimal."""
    pr = ParameterRange(min_val=20, max_val=50)  # type: ignore[arg-type]
    assert isinstance(pr.min_val, Decimal)
    assert isinstance(pr.max_val, Decimal)


def test_parameter_range_invalid_min_gt_max() -> None:
    """ParameterRange raises ValueError when min_val > max_val."""
    with pytest.raises(ValueError, match="min_val"):
        ParameterRange(min_val=Decimal("80"), max_val=Decimal("20"))


# ---------------------------------------------------------------------------
# Tests: run_optimization() — basic
# ---------------------------------------------------------------------------


def test_run_optimization_returns_optimizer_result() -> None:
    """run_optimization returns an OptimizerResult with correct types."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    result = run_optimization(
        base_config=config,
        param_ranges={"buy_level": ParameterRange(Decimal("20"), Decimal("50"))},
        price_series=price_series,
        signal_series=signal_series,
        n_trials=10,
        objective_metric="xirr",
        seed=42,
    )

    assert isinstance(result, OptimizerResult)
    assert result.objective == "xirr"
    assert isinstance(result.best_value, Decimal)
    assert isinstance(result.best_params, dict)
    assert "buy_level" in result.best_params
    assert isinstance(result.best_params["buy_level"], Decimal)


def test_run_optimization_best_params_within_range() -> None:
    """Best params found by optimizer are within the specified range."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()
    min_val = Decimal("20")
    max_val = Decimal("60")

    result = run_optimization(
        base_config=config,
        param_ranges={"buy_level": ParameterRange(min_val, max_val)},
        price_series=price_series,
        signal_series=signal_series,
        n_trials=10,
        objective_metric="xirr",
        seed=42,
    )

    # best_params should be within the specified range
    buy_level = result.best_params["buy_level"]
    assert min_val <= buy_level <= max_val, (
        f"buy_level={buy_level} is outside [{min_val}, {max_val}]"
    )


def test_run_optimization_trial_history_populated() -> None:
    """Trial history is populated with TrialRecord entries."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    result = run_optimization(
        base_config=config,
        param_ranges={"buy_level": ParameterRange(Decimal("20"), Decimal("50"))},
        price_series=price_series,
        signal_series=signal_series,
        n_trials=10,
        objective_metric="xirr",
        seed=42,
    )

    assert len(result.optimization_history) == 10
    for rec in result.optimization_history:
        assert isinstance(rec, TrialRecord)
        assert isinstance(rec.trial_number, int)
        assert isinstance(rec.value, Decimal)
        assert "buy_level" in rec.params
        assert isinstance(rec.params["buy_level"], Decimal)


def test_run_optimization_no_float_in_boundary_values() -> None:
    """All values at the OptimizerResult boundary are Decimal (no float)."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    result = run_optimization(
        base_config=config,
        param_ranges={"buy_level": ParameterRange(Decimal("20"), Decimal("50"))},
        price_series=price_series,
        signal_series=signal_series,
        n_trials=10,
        objective_metric="xirr",
        seed=42,
    )

    # best_value must be Decimal
    assert isinstance(result.best_value, Decimal), (
        f"best_value is {type(result.best_value)}, expected Decimal"
    )

    # All best_params values must be Decimal
    for k, v in result.best_params.items():
        assert isinstance(v, Decimal), f"best_params[{k}] is {type(v)}, expected Decimal"

    # All trial history values must be Decimal
    for rec in result.optimization_history:
        assert isinstance(rec.value, Decimal)
        for k, v in rec.params.items():
            assert isinstance(v, Decimal), f"trial params[{k}] is {type(v)}, expected Decimal"


# ---------------------------------------------------------------------------
# Tests: objective metrics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("objective", ["xirr", "sharpe", "cagr", "sortino"])
def test_run_optimization_each_objective(objective: str) -> None:
    """run_optimization works with each valid objective metric."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    result = run_optimization(
        base_config=config,
        param_ranges={"buy_level": ParameterRange(Decimal("20"), Decimal("60"))},
        price_series=price_series,
        signal_series=signal_series,
        n_trials=10,
        objective_metric=objective,
        seed=42,
    )

    assert result.objective == objective
    assert isinstance(result.best_value, Decimal)


def test_run_optimization_invalid_objective_raises() -> None:
    """run_optimization raises ValueError for unknown objective."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    with pytest.raises(ValueError, match="objective_metric"):
        run_optimization(
            base_config=config,
            param_ranges={"buy_level": ParameterRange(Decimal("20"), Decimal("50"))},
            price_series=price_series,
            signal_series=signal_series,
            n_trials=10,
            objective_metric="invalid_metric",
            seed=42,
        )


# ---------------------------------------------------------------------------
# Tests: validation errors
# ---------------------------------------------------------------------------


def test_run_optimization_empty_param_ranges_raises() -> None:
    """run_optimization raises ValueError when param_ranges is empty."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    with pytest.raises(ValueError, match="param_ranges"):
        run_optimization(
            base_config=config,
            param_ranges={},
            price_series=price_series,
            signal_series=signal_series,
            n_trials=10,
            objective_metric="xirr",
        )


def test_run_optimization_unknown_param_raises() -> None:
    """run_optimization raises ValueError for unknown param names."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    with pytest.raises(ValueError, match="Unknown optimizable parameter"):
        run_optimization(
            base_config=config,
            param_ranges={"unknown_param": ParameterRange(Decimal("20"), Decimal("50"))},
            price_series=price_series,
            signal_series=signal_series,
            n_trials=10,
            objective_metric="xirr",
        )


def test_run_optimization_empty_price_series_raises() -> None:
    """run_optimization raises ValueError when price_series is empty."""
    config = _make_config()
    signal_series = _make_signal_series()

    with pytest.raises(ValueError, match="price_series"):
        run_optimization(
            base_config=config,
            param_ranges={"buy_level": ParameterRange(Decimal("20"), Decimal("50"))},
            price_series=[],
            signal_series=signal_series,
            n_trials=10,
            objective_metric="xirr",
        )


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


def test_run_optimization_all_trials_fail_graceful() -> None:
    """When all trials fail, optimizer returns graceful result with sentinel value."""
    config = _make_config()
    signal_series = _make_signal_series()

    # Use a price_series with only 1 element — BacktestEngine will raise ValueError
    # since there are no common dates between price and signal
    # We simulate all failures by using a price series with dates not in signal series
    from datetime import date as d

    # Price series starting 2 years after signal series ends — no overlap
    no_overlap_prices = [
        (d(2025, 1, 2), Decimal("200")),
        (d(2025, 1, 3), Decimal("201")),
    ]

    result = run_optimization(
        base_config=config,
        param_ranges={"buy_level": ParameterRange(Decimal("20"), Decimal("50"))},
        price_series=no_overlap_prices,
        signal_series=signal_series,
        n_trials=10,
        objective_metric="xirr",
        seed=42,
    )

    # Should not raise — graceful result
    assert isinstance(result, OptimizerResult)
    assert result.best_value == Decimal("-999")
    assert result.n_trials_completed == 0
    assert result.n_trials_failed > 0


def test_run_optimization_multi_param() -> None:
    """Optimizer handles multiple parameters simultaneously."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    result = run_optimization(
        base_config=config,
        param_ranges={
            "buy_level": ParameterRange(Decimal("20"), Decimal("40")),
            "sell_level": ParameterRange(Decimal("60"), Decimal("80")),
        },
        price_series=price_series,
        signal_series=signal_series,
        n_trials=15,
        objective_metric="cagr",
        seed=42,
    )

    assert "buy_level" in result.best_params
    assert "sell_level" in result.best_params
    # Both params in range
    assert Decimal("20") <= result.best_params["buy_level"] <= Decimal("40")
    assert Decimal("60") <= result.best_params["sell_level"] <= Decimal("80")


def test_run_optimization_cooldown_days_integer() -> None:
    """cooldown_days is treated as integer parameter by optimizer."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    result = run_optimization(
        base_config=config,
        param_ranges={
            "cooldown_days": ParameterRange(Decimal("1"), Decimal("60")),
        },
        price_series=price_series,
        signal_series=signal_series,
        n_trials=10,
        objective_metric="xirr",
        seed=42,
    )

    # cooldown_days param should be an integer-valued Decimal
    cd_val = result.best_params["cooldown_days"]
    assert isinstance(cd_val, Decimal)
    # Should be a whole number
    assert cd_val == cd_val.to_integral_value(), f"cooldown_days={cd_val} is not integer-valued"


def test_run_optimization_deterministic_with_seed() -> None:
    """Same seed produces same best_params on identical runs."""
    config = _make_config()
    price_series = _make_price_series()
    signal_series = _make_signal_series()

    kwargs = dict(
        base_config=config,
        param_ranges={"buy_level": ParameterRange(Decimal("20"), Decimal("50"))},
        price_series=price_series,
        signal_series=signal_series,
        n_trials=10,
        objective_metric="xirr",
        seed=42,
    )

    result1 = run_optimization(**kwargs)
    result2 = run_optimization(**kwargs)

    assert result1.best_params == result2.best_params
    assert result1.best_value == result2.best_value


# ---------------------------------------------------------------------------
# Tests: AST scans — no float annotations, no print()
# ---------------------------------------------------------------------------


def test_optimizer_no_float_annotations() -> None:
    """optimizer.py has no bare 'float' type annotations (Decimal not float rule)."""
    assert not _has_float_annotation(str(OPTIMIZER_PATH)), (
        "optimizer.py contains float type annotations — use Decimal at boundaries"
    )


def test_optimizer_no_print_calls() -> None:
    """optimizer.py has no print() calls (structlog only)."""
    assert not _has_print_call(str(OPTIMIZER_PATH)), (
        "optimizer.py contains print() calls — use structlog instead"
    )
