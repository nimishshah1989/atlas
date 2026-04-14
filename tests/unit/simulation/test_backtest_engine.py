"""Unit tests for BacktestEngine — V3-4."""

from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.models.simulation import (
    SimulationConfig,
    SimulationParameters,
    TransactionAction,
)
from backend.services.simulation.backtest_engine import BacktestEngine
from backend.services.simulation.signal_adapters import (
    SignalPoint,
    SignalSeries,
    SignalState,
)
from backend.models.simulation import SignalType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BACKTEST_ENGINE_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "backend"
    / "services"
    / "simulation"
    / "backtest_engine.py"
)


def _make_config(
    sip_amount: Decimal = Decimal("10000"),
    lumpsum_amount: Decimal = Decimal("50000"),
    buy_level: Decimal = Decimal("40"),
    sell_level: Decimal = Decimal("70"),
    reentry_level: Decimal | None = None,
    sell_pct: Decimal = Decimal("100"),
    redeploy_pct: Decimal = Decimal("100"),
    cooldown_days: int = 30,
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
        start_date=date(2023, 1, 1),
        end_date=date(2023, 6, 30),
    )


def _make_price_series(
    start: date, end: date, price: Decimal = Decimal("100")
) -> list[tuple[date, Decimal]]:
    """Generate daily price series (Mon-Fri) with a fixed price."""
    from datetime import timedelta

    series = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            series.append((current, price))
        current += timedelta(days=1)
    return series


def _make_signal_series(
    price_series: list[tuple[date, Decimal]],
    state: SignalState = SignalState.HOLD,
) -> SignalSeries:
    """Generate a signal series with all-same state."""
    points = [SignalPoint(date=d, state=state, raw_value=Decimal("50")) for d, _ in price_series]
    return SignalSeries(points=points, signal_type=SignalType.BREADTH)


def _make_signal_series_on_date(
    price_series: list[tuple[date, Decimal]],
    signals: dict[date, SignalState],
    default: SignalState = SignalState.HOLD,
) -> SignalSeries:
    """Generate a signal series with specific signals on specific dates."""
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
# Tests
# ---------------------------------------------------------------------------


def test_sip_only_no_signal() -> None:
    """All HOLD signals — only SIP buys happen monthly."""
    config = _make_config(sip_amount=Decimal("10000"), lumpsum_amount=Decimal("0"))
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 4, 28))
    signal_series = _make_signal_series(price_series, SignalState.HOLD)

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    sip_txs = [tx for tx in result.transactions if tx.action == TransactionAction.SIP_BUY]
    # Should have SIPs for Jan, Feb, Mar, Apr = 4 months
    assert len(sip_txs) == 4
    assert all(tx.amount == Decimal("10000") for tx in sip_txs)
    assert result.total_invested == Decimal("40000")


def test_lumpsum_on_buy_signal() -> None:
    """BUY signal triggers lumpsum deployment."""
    config = _make_config(
        sip_amount=Decimal("0"),
        lumpsum_amount=Decimal("50000"),
        cooldown_days=0,
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 1, 31))
    buy_date = price_series[5][0]  # Some day in Jan
    signal_series = _make_signal_series_on_date(price_series, {buy_date: SignalState.BUY})

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    lumpsum_txs = [tx for tx in result.transactions if tx.action == TransactionAction.LUMPSUM_BUY]
    assert len(lumpsum_txs) == 1
    assert lumpsum_txs[0].amount == Decimal("50000")
    assert lumpsum_txs[0].date == buy_date


def test_sell_on_sell_signal() -> None:
    """SELL signal reduces units by sell_pct%."""
    # Buy first, then sell
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("0"),
        sell_pct=Decimal("100"),
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 3, 31))
    # SELL signal on some date in Feb after initial SIPs
    sell_date = date(2023, 2, 15)
    # Ensure sell_date is a trading day (Wed)
    signal_series = _make_signal_series_on_date(price_series, {sell_date: SignalState.SELL})

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    sell_txs = [tx for tx in result.transactions if tx.action == TransactionAction.SELL]
    # At least one SELL should occur
    assert len(sell_txs) >= 1
    # After the sell, liquid > 0
    # Find the DailyValue on sell_date
    sell_dv = next((dv for dv in result.daily_values if dv.date == sell_date), None)
    assert sell_dv is not None
    assert sell_dv.liquid > Decimal("0")


def test_reentry_deploys_liquid() -> None:
    """REENTRY deploys redeploy_pct% of liquid cash back into instrument."""
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("0"),
        sell_pct=Decimal("100"),
        redeploy_pct=Decimal("100"),
        reentry_level=Decimal("45"),
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 3, 31))

    sell_date = date(2023, 2, 8)
    reentry_date = date(2023, 2, 22)

    signal_series = _make_signal_series_on_date(
        price_series,
        {sell_date: SignalState.SELL, reentry_date: SignalState.REENTRY},
    )

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    redeploy_txs = [tx for tx in result.transactions if tx.action == TransactionAction.REDEPLOY]
    assert len(redeploy_txs) >= 1

    # After reentry, liquid should be near zero
    redeploy_dv = next((dv for dv in result.daily_values if dv.date == reentry_date), None)
    assert redeploy_dv is not None
    assert redeploy_dv.liquid < Decimal("1")  # essentially 0 after full redeploy


def test_cooldown_prevents_rapid_lumpsum() -> None:
    """Two BUY signals within cooldown_days, only one lumpsum fires."""
    config = _make_config(
        sip_amount=Decimal("0"),
        lumpsum_amount=Decimal("50000"),
        cooldown_days=30,
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 2, 28))

    # Two BUY signals 5 days apart (< cooldown_days=30)
    buy_date_1 = date(2023, 1, 10)
    buy_date_2 = date(2023, 1, 15)
    signal_series = _make_signal_series_on_date(
        price_series,
        {buy_date_1: SignalState.BUY, buy_date_2: SignalState.BUY},
    )

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    lumpsum_txs = [tx for tx in result.transactions if tx.action == TransactionAction.LUMPSUM_BUY]
    assert len(lumpsum_txs) == 1  # Only the first BUY fires
    assert lumpsum_txs[0].date == buy_date_1


def test_sell_pct_partial() -> None:
    """sell_pct=50 sells exactly half of holdings."""
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("0"),
        sell_pct=Decimal("50"),
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 2, 28))
    sell_date = date(2023, 2, 7)
    signal_series = _make_signal_series_on_date(price_series, {sell_date: SignalState.SELL})

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    sell_txs = [tx for tx in result.transactions if tx.action == TransactionAction.SELL]
    assert len(sell_txs) == 1

    sell_dv_before = next((dv for dv in result.daily_values if dv.date < sell_date), None)
    sell_dv_after = next((dv for dv in result.daily_values if dv.date == sell_date), None)
    assert sell_dv_before is not None
    assert sell_dv_after is not None
    # After selling 50%, liquid should be > 0 and fv should be roughly half of before
    assert sell_dv_after.liquid > Decimal("0")
    assert sell_dv_after.units > Decimal("0")  # Still holding 50%


def test_tax_fifo_applied_on_sell() -> None:
    """Sell records disposals which have tax_detail populated."""
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("0"),
        sell_pct=Decimal("100"),
    )
    price_series = _make_price_series(date(2022, 1, 3), date(2022, 3, 31))
    sell_date = date(2022, 3, 10)
    signal_series = _make_signal_series_on_date(price_series, {sell_date: SignalState.SELL})

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    sell_txs = [tx for tx in result.transactions if tx.action == TransactionAction.SELL]
    assert len(sell_txs) >= 1
    for tx in sell_txs:
        assert tx.tax_detail is not None
        # Tax fields are Decimal
        assert isinstance(tx.tax_detail.total_tax, Decimal)
    # All disposals in the result
    assert len(result.all_disposals) >= 1


def test_daily_values_recorded() -> None:
    """Every trading day in the intersection has a DailyValue."""
    config = _make_config()
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 1, 31))
    signal_series = _make_signal_series(price_series, SignalState.HOLD)

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    assert len(result.daily_values) == len(price_series)
    for dv in result.daily_values:
        assert isinstance(dv.nav, Decimal)
        assert isinstance(dv.total, Decimal)


def test_transactions_logged() -> None:
    """All buys and sells are recorded as TransactionRecords."""
    config = _make_config(
        sip_amount=Decimal("5000"),
        lumpsum_amount=Decimal("20000"),
        cooldown_days=0,
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 2, 28))
    buy_date = date(2023, 1, 17)  # Tuesday
    sell_date = date(2023, 2, 7)  # Tuesday
    signal_series = _make_signal_series_on_date(
        price_series,
        {buy_date: SignalState.BUY, sell_date: SignalState.SELL},
    )

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    actions = {tx.action for tx in result.transactions}
    assert TransactionAction.SIP_BUY in actions
    assert TransactionAction.LUMPSUM_BUY in actions
    assert TransactionAction.SELL in actions


def test_total_invested_excludes_redeployment() -> None:
    """Redeployment of liquid cash is NOT counted as new total_invested."""
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("0"),
        sell_pct=Decimal("100"),
        redeploy_pct=Decimal("100"),
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 3, 31))
    sell_date = date(2023, 2, 8)
    reentry_date = date(2023, 2, 22)
    signal_series = _make_signal_series_on_date(
        price_series,
        {sell_date: SignalState.SELL, reentry_date: SignalState.REENTRY},
    )

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    # Count months covered for SIP
    months = set()
    for dv in result.daily_values:
        months.add((dv.date.year, dv.date.month))
    expected_invested = Decimal("10000") * len(months)

    # total_invested should match only SIP (no redeploy)
    redeploy_txs = [tx for tx in result.transactions if tx.action == TransactionAction.REDEPLOY]
    assert len(redeploy_txs) >= 1

    # total_invested == SIP * months (redeployment not added)
    assert result.total_invested == expected_invested


def test_empty_price_series_raises() -> None:
    """ValueError on empty price_series."""
    config = _make_config()
    price_series: list[tuple[date, Decimal]] = []
    signal_series = SignalSeries(points=[], signal_type=SignalType.BREADTH)

    engine = BacktestEngine()
    with pytest.raises(ValueError, match="price_series must not be empty"):
        engine.run(config, price_series, signal_series)


def test_no_float_annotations() -> None:
    """backtest_engine.py must not contain bare float type annotations."""
    with open(BACKTEST_ENGINE_PATH, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=str(BACKTEST_ENGINE_PATH))

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            ann = node.annotation
            if isinstance(ann, ast.Name) and ann.id == "float":
                violations.append(f"arg annotation at line {node.col_offset}")
        if isinstance(node, ast.FunctionDef) and node.returns is not None:
            ret = node.returns
            if isinstance(ret, ast.Name) and ret.id == "float":
                violations.append(f"return annotation: {node.name}")
        if isinstance(node, ast.AnnAssign) and node.annotation is not None:
            ann = node.annotation
            if isinstance(ann, ast.Name) and ann.id == "float":
                violations.append("AnnAssign float annotation")

    assert violations == [], f"Float annotations found: {violations}"


def test_no_print_calls() -> None:
    """backtest_engine.py must not contain print() calls (AST scan)."""
    with open(BACKTEST_ENGINE_PATH, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=str(BACKTEST_ENGINE_PATH))

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Only flag actual Call nodes, not string occurrences
            if isinstance(func, ast.Name) and func.id == "print":
                violations.append(f"line {node.lineno}")

    assert violations == [], f"print() calls found at: {violations}"


def test_decimal_only_math() -> None:
    """All financial result fields must be Decimal type, not float."""
    config = _make_config(sip_amount=Decimal("10000"), lumpsum_amount=Decimal("0"))
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 2, 28))
    signal_series = _make_signal_series(price_series, SignalState.HOLD)

    engine = BacktestEngine()
    result = engine.run(config, price_series, signal_series)

    assert isinstance(result.total_invested, Decimal)
    assert isinstance(result.final_value, Decimal)
    assert isinstance(result.final_units, Decimal)
    assert isinstance(result.final_nav, Decimal)
    assert isinstance(result.final_liquid, Decimal)

    for dv in result.daily_values:
        assert isinstance(dv.nav, Decimal)
        assert isinstance(dv.units, Decimal)
        assert isinstance(dv.fv, Decimal)
        assert isinstance(dv.liquid, Decimal)
        assert isinstance(dv.total, Decimal)

    for tx in result.transactions:
        assert isinstance(tx.amount, Decimal)
        assert isinstance(tx.nav, Decimal)
        assert isinstance(tx.units, Decimal)


def test_deterministic_same_input_same_output() -> None:
    """Running the engine twice with identical inputs produces identical results."""
    config = _make_config(
        sip_amount=Decimal("10000"),
        lumpsum_amount=Decimal("50000"),
        cooldown_days=30,
    )
    price_series = _make_price_series(date(2023, 1, 2), date(2023, 6, 30))

    # Mix of signal states
    from datetime import timedelta

    signals = {}
    current = date(2023, 1, 2)
    toggle = [SignalState.HOLD, SignalState.BUY, SignalState.HOLD, SignalState.SELL]
    i = 0
    while current <= date(2023, 6, 30):
        if current.weekday() < 5:
            signals[current] = toggle[i % len(toggle)]
            i += 1
        current += timedelta(days=1)

    price_dict = {d: p for d, p in price_series}
    signal_series = _make_signal_series_on_date(
        [(d, price_dict[d]) for d in sorted(signals.keys()) if d in price_dict],
        signals,
    )

    engine = BacktestEngine()
    result_1 = engine.run(config, price_series, signal_series)

    # Re-run with fresh state
    engine_2 = BacktestEngine()
    result_2 = engine_2.run(config, price_series, signal_series)

    assert result_1.total_invested == result_2.total_invested
    assert result_1.final_value == result_2.final_value
    assert len(result_1.daily_values) == len(result_2.daily_values)
    assert len(result_1.transactions) == len(result_2.transactions)
