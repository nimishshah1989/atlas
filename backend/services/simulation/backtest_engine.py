"""Backtest Engine — pure computation module for V3 Simulation Engine.

No DB, no I/O, no async. Walks day-by-day through a date range and
executes a signal-driven SIP + lumpsum investment strategy.

Strategy rules:
  SIP:      1st trading day of each month → invest sip_amount
  BUY:      Signal BUY + cooldown satisfied → invest lumpsum_amount
  SELL:     Signal SELL → sell sell_pct% of holdings; proceeds → liquid
  REENTRY:  Signal REENTRY → redeploy redeploy_pct% of liquid back in

All arithmetic in Decimal — NEVER float.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from backend.models.simulation import (
    DailyValue,
    SimulationConfig,
    SimulationParameters,
    TransactionAction,
    TransactionRecord,
)
from backend.services.simulation.signal_adapters import SignalSeries, SignalState
from backend.services.simulation.tax_engine import FIFOLotTracker, LotDisposal


# ---------------------------------------------------------------------------
# BacktestResult dataclass — raw output before analytics
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    """Raw output from BacktestEngine.run(), consumed by analytics module."""

    daily_values: list[DailyValue]
    transactions: list[TransactionRecord]
    all_disposals: list[LotDisposal]  # For tax summary computation
    total_invested: Decimal
    final_value: Decimal  # Market value of units at last date
    final_units: Decimal
    final_nav: Decimal
    final_liquid: Decimal


# ---------------------------------------------------------------------------
# BacktestEngine
# ---------------------------------------------------------------------------


@dataclass
class _DayState:
    """Mutable state carried across simulation days."""

    lot_tracker: FIFOLotTracker
    liquid: Decimal = Decimal("0")
    total_invested: Decimal = Decimal("0")
    last_lumpsum_date: Optional[date] = None
    daily_values: list[DailyValue] = field(default_factory=list)
    transactions: list[TransactionRecord] = field(default_factory=list)
    all_disposals: list[LotDisposal] = field(default_factory=list)
    sip_months_done: set[tuple[int, int]] = field(default_factory=set)


class BacktestEngine:
    """Pure-computation backtest engine. No DB, no IO, no async."""

    def run(
        self,
        config: SimulationConfig,
        price_series: list[tuple[date, Decimal]],
        signal_series: SignalSeries,
    ) -> BacktestResult:
        """Execute the backtest and return raw results."""
        if not price_series:
            raise ValueError("price_series must not be empty")

        price_map: dict[date, Decimal] = {d: p for d, p in price_series}
        signal_map: dict[date, SignalState] = {pt.date: pt.state for pt in signal_series}
        common_dates: list[date] = sorted(price_map.keys() & signal_map.keys())

        if not common_dates:
            raise ValueError("No overlapping dates between price_series and signal_series")

        state = _DayState(lot_tracker=FIFOLotTracker())
        params = config.parameters

        for today in common_dates:
            nav = price_map[today]
            signal = signal_map[today]
            _process_day(state, params, today, nav, signal)

        last_day = state.daily_values[-1]
        return BacktestResult(
            daily_values=state.daily_values,
            transactions=state.transactions,
            all_disposals=state.all_disposals,
            total_invested=state.total_invested,
            final_value=last_day.fv,
            final_units=last_day.units,
            final_nav=last_day.nav,
            final_liquid=last_day.liquid,
        )


def _process_day(
    state: _DayState,
    params: SimulationParameters,
    today: date,
    nav: Decimal,
    signal: SignalState,
) -> None:
    """Process a single day: SIP, lumpsum/sell/reentry, snapshot."""
    ym = (today.year, today.month)

    # SIP on 1st trading day of each month
    if ym not in state.sip_months_done and params.sip_amount > Decimal("0"):
        state.sip_months_done.add(ym)
        sip_units = params.sip_amount / nav
        state.lot_tracker.add_lot(buy_date=today, units=sip_units, cost_per_unit=nav)
        state.total_invested += params.sip_amount
        state.transactions.append(
            TransactionRecord(
                date=today,
                action=TransactionAction.SIP_BUY,
                amount=params.sip_amount,
                nav=nav,
                units=sip_units,
                tax_detail=None,
            )
        )

    # Lumpsum on BUY signal (with cooldown)
    if (
        signal == SignalState.BUY
        and params.lumpsum_amount > Decimal("0")
        and _cooldown_ok(today, state.last_lumpsum_date, params.cooldown_days)
    ):
        _handle_lumpsum(state, params, today, nav)
    elif signal == SignalState.SELL and state.lot_tracker.total_units > Decimal("0"):
        _handle_sell(state, params, today, nav)
    elif signal == SignalState.REENTRY and state.liquid > Decimal("0"):
        _handle_reentry(state, params, today, nav)

    # Daily snapshot
    current_units = state.lot_tracker.total_units
    fv = current_units * nav
    state.daily_values.append(
        DailyValue(
            date=today,
            nav=nav,
            units=current_units,
            fv=fv,
            liquid=state.liquid,
            total=fv + state.liquid,
        )
    )


def _handle_lumpsum(
    state: _DayState,
    params: SimulationParameters,
    today: date,
    nav: Decimal,
) -> None:
    """Execute a lumpsum buy."""
    units = params.lumpsum_amount / nav
    state.lot_tracker.add_lot(buy_date=today, units=units, cost_per_unit=nav)
    state.total_invested += params.lumpsum_amount
    state.last_lumpsum_date = today
    state.transactions.append(
        TransactionRecord(
            date=today,
            action=TransactionAction.LUMPSUM_BUY,
            amount=params.lumpsum_amount,
            nav=nav,
            units=units,
            tax_detail=None,
        )
    )


def _handle_sell(
    state: _DayState,
    params: SimulationParameters,
    today: date,
    nav: Decimal,
) -> None:
    """Execute a sell at sell_pct of holdings."""
    from backend.models.simulation import TaxDetail

    total_units_held = state.lot_tracker.total_units
    sell_pct = max(Decimal("0"), min(Decimal("100"), params.sell_pct))
    units_to_sell = (total_units_held * sell_pct / Decimal("100")).quantize(Decimal("0.0000001"))
    units_to_sell = min(units_to_sell, total_units_held)

    if units_to_sell <= Decimal("0"):
        return

    disposals = state.lot_tracker.sell_units(
        sell_date=today,
        units_to_sell=units_to_sell,
        sell_price_per_unit=nav,
    )
    state.all_disposals.extend(disposals)

    total_tax = sum((d.tax_detail.total_tax for d in disposals), Decimal("0"))
    gross_proceeds = units_to_sell * nav
    state.liquid += gross_proceeds - total_tax

    state.transactions.append(
        TransactionRecord(
            date=today,
            action=TransactionAction.SELL,
            amount=gross_proceeds,
            nav=nav,
            units=units_to_sell,
            tax_detail=TaxDetail(
                stcg_tax=sum((d.tax_detail.stcg_tax for d in disposals), Decimal("0")),
                ltcg_tax=sum((d.tax_detail.ltcg_tax for d in disposals), Decimal("0")),
                cess=sum((d.tax_detail.cess for d in disposals), Decimal("0")),
                total_tax=total_tax,
            ),
        )
    )


def _handle_reentry(
    state: _DayState,
    params: SimulationParameters,
    today: date,
    nav: Decimal,
) -> None:
    """Redeploy liquid on REENTRY signal."""
    redeploy_pct = max(Decimal("0"), min(Decimal("100"), params.redeploy_pct))
    redeploy_amount = state.liquid * redeploy_pct / Decimal("100")
    if redeploy_amount <= Decimal("0"):
        return
    units = redeploy_amount / nav
    state.lot_tracker.add_lot(buy_date=today, units=units, cost_per_unit=nav)
    state.liquid -= redeploy_amount
    state.transactions.append(
        TransactionRecord(
            date=today,
            action=TransactionAction.REDEPLOY,
            amount=redeploy_amount,
            nav=nav,
            units=units,
            tax_detail=None,
        )
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cooldown_ok(
    today: date,
    last_lumpsum_date: Optional[date],
    cooldown_days: int,
) -> bool:
    """Return True if cooldown_days have elapsed since the last lumpsum."""
    if last_lumpsum_date is None:
        return True
    return (today - last_lumpsum_date).days >= cooldown_days


# ---------------------------------------------------------------------------
# Utility: AST scan for float annotations (used in tests)
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
    "BacktestEngine",
    "BacktestResult",
    "_cooldown_ok",
    "_has_float_annotation",
]
