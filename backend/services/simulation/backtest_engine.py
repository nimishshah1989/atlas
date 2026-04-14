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
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from backend.models.simulation import (
    DailyValue,
    SimulationConfig,
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


class BacktestEngine:
    """Pure-computation backtest engine. No DB, no IO, no async.

    Takes price_series (list of (date, Decimal) tuples) and signal_series
    (SignalSeries) and config (SimulationConfig), walks day-by-day, applies
    buy/sell logic per spec §8.
    """

    def run(
        self,
        config: SimulationConfig,
        price_series: list[tuple[date, Decimal]],
        signal_series: SignalSeries,
    ) -> BacktestResult:
        """Execute the backtest and return raw results."""
        if not price_series:
            raise ValueError("price_series must not be empty")

        params = config.parameters

        # Build lookup maps for fast access
        price_map: dict[date, Decimal] = {d: p for d, p in price_series}
        signal_map: dict[date, SignalState] = {pt.date: pt.state for pt in signal_series}

        # Only process dates present in BOTH price_series AND signal_series
        common_dates: list[date] = sorted(price_map.keys() & signal_map.keys())

        if not common_dates:
            raise ValueError("No overlapping dates between price_series and signal_series")

        # State variables
        lot_tracker = FIFOLotTracker()
        liquid: Decimal = Decimal("0")
        total_invested: Decimal = Decimal("0")
        last_lumpsum_date: Optional[date] = None

        daily_values: list[DailyValue] = []
        transactions: list[TransactionRecord] = []
        all_disposals: list[LotDisposal] = []

        # Track which (year, month) we've already done a SIP for
        sip_months_done: set[tuple[int, int]] = set()

        for today in common_dates:
            nav = price_map[today]
            signal = signal_map[today]
            ym = (today.year, today.month)

            # --- SIP on 1st trading day of each month ---
            if ym not in sip_months_done and params.sip_amount > Decimal("0"):
                sip_months_done.add(ym)
                sip_units = params.sip_amount / nav
                lot_tracker.add_lot(
                    buy_date=today,
                    units=sip_units,
                    cost_per_unit=nav,
                )
                total_invested += params.sip_amount
                transactions.append(
                    TransactionRecord(
                        date=today,
                        action=TransactionAction.SIP_BUY,
                        amount=params.sip_amount,
                        nav=nav,
                        units=sip_units,
                        tax_detail=None,
                    )
                )

            # --- Lumpsum on BUY signal (with cooldown) ---
            if (
                signal == SignalState.BUY
                and params.lumpsum_amount > Decimal("0")
                and _cooldown_ok(today, last_lumpsum_date, params.cooldown_days)
            ):
                lumpsum_units = params.lumpsum_amount / nav
                lot_tracker.add_lot(
                    buy_date=today,
                    units=lumpsum_units,
                    cost_per_unit=nav,
                )
                total_invested += params.lumpsum_amount
                last_lumpsum_date = today
                transactions.append(
                    TransactionRecord(
                        date=today,
                        action=TransactionAction.LUMPSUM_BUY,
                        amount=params.lumpsum_amount,
                        nav=nav,
                        units=lumpsum_units,
                        tax_detail=None,
                    )
                )

            # --- Sell on SELL signal ---
            elif signal == SignalState.SELL and lot_tracker.total_units > Decimal("0"):
                total_units_held = lot_tracker.total_units
                # Clamp sell_pct to 0-100 range
                sell_pct = max(Decimal("0"), min(Decimal("100"), params.sell_pct))
                units_to_sell = (total_units_held * sell_pct / Decimal("100")).quantize(
                    Decimal("0.0000001")
                )
                # Ensure we don't exceed held units due to rounding
                units_to_sell = min(units_to_sell, total_units_held)

                if units_to_sell > Decimal("0"):
                    disposals = lot_tracker.sell_units(
                        sell_date=today,
                        units_to_sell=units_to_sell,
                        sell_price_per_unit=nav,
                    )
                    all_disposals.extend(disposals)

                    # Total tax from all disposals in this sell event
                    total_tax = sum((d.tax_detail.total_tax for d in disposals), Decimal("0"))
                    gross_proceeds = units_to_sell * nav
                    net_proceeds = gross_proceeds - total_tax
                    liquid += net_proceeds

                    # Aggregate tax_detail for the TransactionRecord
                    from backend.models.simulation import TaxDetail

                    agg_stcg = sum((d.tax_detail.stcg_tax for d in disposals), Decimal("0"))
                    agg_ltcg = sum((d.tax_detail.ltcg_tax for d in disposals), Decimal("0"))
                    agg_cess = sum((d.tax_detail.cess for d in disposals), Decimal("0"))

                    transactions.append(
                        TransactionRecord(
                            date=today,
                            action=TransactionAction.SELL,
                            amount=gross_proceeds,
                            nav=nav,
                            units=units_to_sell,
                            tax_detail=TaxDetail(
                                stcg_tax=agg_stcg,
                                ltcg_tax=agg_ltcg,
                                cess=agg_cess,
                                total_tax=total_tax,
                            ),
                        )
                    )

            # --- Redeploy on REENTRY signal ---
            elif signal == SignalState.REENTRY and liquid > Decimal("0"):
                redeploy_pct = max(Decimal("0"), min(Decimal("100"), params.redeploy_pct))
                redeploy_amount = liquid * redeploy_pct / Decimal("100")
                if redeploy_amount > Decimal("0"):
                    redeploy_units = redeploy_amount / nav
                    lot_tracker.add_lot(
                        buy_date=today,
                        units=redeploy_units,
                        cost_per_unit=nav,
                    )
                    liquid -= redeploy_amount
                    # Redeployment does NOT count toward total_invested
                    transactions.append(
                        TransactionRecord(
                            date=today,
                            action=TransactionAction.REDEPLOY,
                            amount=redeploy_amount,
                            nav=nav,
                            units=redeploy_units,
                            tax_detail=None,
                        )
                    )

            # --- Daily snapshot ---
            current_units = lot_tracker.total_units
            fv = current_units * nav
            total_portfolio = fv + liquid

            daily_values.append(
                DailyValue(
                    date=today,
                    nav=nav,
                    units=current_units,
                    fv=fv,
                    liquid=liquid,
                    total=total_portfolio,
                )
            )

        # Final state
        last_day = daily_values[-1]
        return BacktestResult(
            daily_values=daily_values,
            transactions=transactions,
            all_disposals=all_disposals,
            total_invested=total_invested,
            final_value=last_day.fv,
            final_units=last_day.units,
            final_nav=last_day.nav,
            final_liquid=last_day.liquid,
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
