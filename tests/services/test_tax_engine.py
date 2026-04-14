"""Golden fixture tests for backend/services/simulation/tax_engine.py.

All financial comparisons use exact Decimal equality (never pytest.approx).
Spec §8: Indian FIFO capital gains tax engine.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from backend.services.simulation.tax_engine import (
    FIFOLotTracker,
    LotDisposal,
    TaxLot,
    _has_float_annotation,
    compute_annual_tax_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tracker(*lots: tuple[date, Decimal, Decimal]) -> FIFOLotTracker:
    """Create FIFOLotTracker pre-loaded with (buy_date, units, cost_per_unit) tuples."""
    tracker = FIFOLotTracker()
    for buy_date, units, cpu in lots:
        tracker.add_lot(buy_date, units, cpu)
    return tracker


def _make_disposal(
    buy_date: date,
    units_bought: Decimal,
    cost_per_unit: Decimal,
    units_sold: Decimal,
    sell_price_per_unit: Decimal,
    sell_date: date,
) -> LotDisposal:
    """Build a single LotDisposal for direct tax computation tests."""
    lot = TaxLot(
        buy_date=buy_date,
        units=units_bought,
        cost_per_unit=cost_per_unit,
    )
    return LotDisposal(
        lot=lot,
        units_sold=units_sold,
        sell_price_per_unit=sell_price_per_unit,
        sell_date=sell_date,
    )


# ---------------------------------------------------------------------------
# test 1: FIFO lot order
# ---------------------------------------------------------------------------


def test_fifo_lot_order() -> None:
    """Buy 100@₹10 then 50@₹20. Sell 120. First lot fully consumed, second partially."""
    tracker = _make_tracker(
        (date(2024, 1, 1), Decimal("100"), Decimal("10")),
        (date(2024, 2, 1), Decimal("50"), Decimal("20")),
    )

    disposals = tracker.sell_units(
        sell_date=date(2024, 12, 1),
        units_to_sell=Decimal("120"),
        sell_price_per_unit=Decimal("15"),
    )

    assert len(disposals) == 2

    # First disposal: all 100 from lot-1 (₹10 cost)
    d0 = disposals[0]
    assert d0.units_sold == Decimal("100")
    assert d0.lot.cost_per_unit == Decimal("10")
    assert d0.cost_basis == Decimal("1000")  # 100 * 10

    # Second disposal: 20 from lot-2 (₹20 cost)
    d1 = disposals[1]
    assert d1.units_sold == Decimal("20")
    assert d1.lot.cost_per_unit == Decimal("20")
    assert d1.cost_basis == Decimal("400")  # 20 * 20

    # 30 units of lot-2 remain
    assert tracker.total_units == Decimal("30")


# ---------------------------------------------------------------------------
# test 2: pre-budget STCG (sell < 2024-07-23, hold 5 months)
# ---------------------------------------------------------------------------


def test_pre_budget_stcg() -> None:
    """Buy 2024-01-01, sell 2024-06-01 (151 days). STCG at 15% + 4% cess."""
    disposal = _make_disposal(
        buy_date=date(2024, 1, 1),
        units_bought=Decimal("100"),
        cost_per_unit=Decimal("100"),
        units_sold=Decimal("100"),
        sell_price_per_unit=Decimal("150"),
        sell_date=date(2024, 6, 1),
    )

    assert not disposal.is_ltcg
    # gain = 100 * (150 - 100) = 5000
    assert disposal.gain == Decimal("5000")

    td = disposal.tax_detail
    # STCG = 5000 * 0.15 = 750
    assert td.stcg_tax == Decimal("750")
    assert td.ltcg_tax == Decimal("0")
    # cess = 750 * 0.04 = 30
    assert td.cess == Decimal("30")
    assert td.total_tax == Decimal("780")


# ---------------------------------------------------------------------------
# test 3: pre-budget LTCG (sell < 2024-07-23, hold 17 months)
# ---------------------------------------------------------------------------


def test_pre_budget_ltcg() -> None:
    """Buy 2023-01-01, sell 2024-06-01 (517 days). LTCG at 10% + 4% cess."""
    disposal = _make_disposal(
        buy_date=date(2023, 1, 1),
        units_bought=Decimal("100"),
        cost_per_unit=Decimal("100"),
        units_sold=Decimal("100"),
        sell_price_per_unit=Decimal("200"),
        sell_date=date(2024, 6, 1),
    )

    assert disposal.is_ltcg
    # gain = 100 * (200 - 100) = 10000
    assert disposal.gain == Decimal("10000")

    td = disposal.tax_detail
    assert td.stcg_tax == Decimal("0")
    # LTCG = 10000 * 0.10 = 1000
    assert td.ltcg_tax == Decimal("1000")
    # cess = 1000 * 0.04 = 40
    assert td.cess == Decimal("40")
    assert td.total_tax == Decimal("1040")


# ---------------------------------------------------------------------------
# test 4: post-budget STCG (sell >= 2024-07-23, hold 6 months)
# ---------------------------------------------------------------------------


def test_post_budget_stcg() -> None:
    """Buy 2024-06-01, sell 2024-12-01 (183 days). STCG at 20% + 4% cess."""
    disposal = _make_disposal(
        buy_date=date(2024, 6, 1),
        units_bought=Decimal("100"),
        cost_per_unit=Decimal("100"),
        units_sold=Decimal("100"),
        sell_price_per_unit=Decimal("150"),
        sell_date=date(2024, 12, 1),
    )

    assert not disposal.is_ltcg
    assert disposal.gain == Decimal("5000")

    td = disposal.tax_detail
    # STCG = 5000 * 0.20 = 1000
    assert td.stcg_tax == Decimal("1000")
    assert td.ltcg_tax == Decimal("0")
    # cess = 1000 * 0.04 = 40
    assert td.cess == Decimal("40")
    assert td.total_tax == Decimal("1040")


# ---------------------------------------------------------------------------
# test 5: post-budget LTCG (sell >= 2024-07-23, hold 18 months)
# ---------------------------------------------------------------------------


def test_post_budget_ltcg() -> None:
    """Buy 2023-06-01, sell 2024-12-01 (549 days). LTCG at 12.5% + 4% cess."""
    disposal = _make_disposal(
        buy_date=date(2023, 6, 1),
        units_bought=Decimal("100"),
        cost_per_unit=Decimal("100"),
        units_sold=Decimal("100"),
        sell_price_per_unit=Decimal("200"),
        sell_date=date(2024, 12, 1),
    )

    assert disposal.is_ltcg
    assert disposal.gain == Decimal("10000")

    td = disposal.tax_detail
    assert td.stcg_tax == Decimal("0")
    # LTCG = 10000 * 0.125 = 1250
    assert td.ltcg_tax == Decimal("1250")
    # cess = 1250 * 0.04 = 50
    assert td.cess == Decimal("50")
    assert td.total_tax == Decimal("1300")


# ---------------------------------------------------------------------------
# test 6: cess is exactly 4% of (stcg_tax + ltcg_tax)
# ---------------------------------------------------------------------------


def test_cess_applied() -> None:
    """Cess must be exactly 4% of gross tax in all cases."""
    for sell_date, expected_rate, is_ltcg_scenario in [
        (date(2024, 6, 1), Decimal("0.15"), False),  # pre-budget STCG
        (date(2024, 6, 1), Decimal("0.10"), True),  # pre-budget LTCG
        (date(2024, 12, 1), Decimal("0.20"), False),  # post-budget STCG
        (date(2024, 12, 1), Decimal("0.125"), True),  # post-budget LTCG
    ]:
        if is_ltcg_scenario:
            buy_date = sell_date.replace(year=sell_date.year - 2)
        else:
            buy_date = sell_date.replace(month=sell_date.month - 3 if sell_date.month > 3 else 12)

        disposal = _make_disposal(
            buy_date=buy_date,
            units_bought=Decimal("100"),
            cost_per_unit=Decimal("100"),
            units_sold=Decimal("100"),
            sell_price_per_unit=Decimal("200"),
            sell_date=sell_date,
        )

        td = disposal.tax_detail
        gross_tax = td.stcg_tax + td.ltcg_tax
        expected_cess = gross_tax * Decimal("0.04")
        assert td.cess == expected_cess, f"Cess mismatch for sell_date={sell_date}"
        assert td.total_tax == gross_tax + td.cess


# ---------------------------------------------------------------------------
# test 7: pre-budget LTCG exemption (₹1L)
# ---------------------------------------------------------------------------


def test_ltcg_exemption_pre_budget() -> None:
    """LTCG gain ₹1,50,000 with ₹1L exemption → only ₹50,000 taxable at 10%."""
    # Create tracker and sell with a pre-budget date
    tracker = _make_tracker(
        (date(2022, 1, 1), Decimal("1000"), Decimal("100")),
    )
    disposals = tracker.sell_units(
        sell_date=date(2024, 6, 1),
        units_to_sell=Decimal("1000"),
        sell_price_per_unit=Decimal("250"),
    )
    # gain = 1000 * (250 - 100) = 150,000

    summary = compute_annual_tax_summary(
        disposals=disposals,
        financial_year_start=date(2024, 4, 1),
    )

    assert summary.ltcg == Decimal("150000")
    # taxable LTCG = 150000 - 100000 = 50000
    # LTCG tax = 50000 * 0.10 = 5000
    # cess = 5000 * 0.04 = 200
    # total = 5200
    assert summary.total_tax == Decimal("5200")


# ---------------------------------------------------------------------------
# test 8: post-budget LTCG exemption (₹1.25L)
# ---------------------------------------------------------------------------


def test_ltcg_exemption_post_budget() -> None:
    """LTCG gain ₹2,00,000 with ₹1.25L exemption → ₹75,000 taxable at 12.5%."""
    tracker = _make_tracker(
        (date(2022, 6, 1), Decimal("1000"), Decimal("100")),
    )
    disposals = tracker.sell_units(
        sell_date=date(2024, 12, 1),
        units_to_sell=Decimal("1000"),
        sell_price_per_unit=Decimal("300"),
    )
    # gain = 1000 * (300 - 100) = 200,000

    summary = compute_annual_tax_summary(
        disposals=disposals,
        financial_year_start=date(2024, 4, 1),
    )

    assert summary.ltcg == Decimal("200000")
    # taxable LTCG = 200000 - 125000 = 75000
    # LTCG tax = 75000 * 0.125 = 9375
    # cess = 9375 * 0.04 = 375
    # total = 9750
    assert summary.total_tax == Decimal("9750")


# ---------------------------------------------------------------------------
# test 9: loss produces zero tax
# ---------------------------------------------------------------------------


def test_loss_no_tax() -> None:
    """Sell at a loss: no tax, all TaxDetail fields are zero."""
    disposal = _make_disposal(
        buy_date=date(2024, 1, 1),
        units_bought=Decimal("100"),
        cost_per_unit=Decimal("200"),
        units_sold=Decimal("100"),
        sell_price_per_unit=Decimal("150"),  # below cost
        sell_date=date(2024, 12, 1),
    )

    assert disposal.gain == Decimal("-5000")
    td = disposal.tax_detail
    assert td.stcg_tax == Decimal("0")
    assert td.ltcg_tax == Decimal("0")
    assert td.cess == Decimal("0")
    assert td.total_tax == Decimal("0")


# ---------------------------------------------------------------------------
# test 10: unrealized gains
# ---------------------------------------------------------------------------


def test_unrealized_gains() -> None:
    """Unrealized gain = sum of (remaining_units * (current_price - cost_per_unit))."""
    tracker = _make_tracker(
        (date(2023, 1, 1), Decimal("100"), Decimal("50")),  # lot 1
        (date(2023, 6, 1), Decimal("200"), Decimal("80")),  # lot 2
    )
    current_price = Decimal("100")

    # Lot 1 unrealized: 100 * (100 - 50) = 5000
    # Lot 2 unrealized: 200 * (100 - 80) = 4000
    # Total = 9000
    assert tracker.unrealized_gains(date(2024, 1, 1), current_price) == Decimal("9000")

    # Sell 50 from lot 1 (FIFO)
    tracker.sell_units(
        sell_date=date(2024, 1, 1),
        units_to_sell=Decimal("50"),
        sell_price_per_unit=current_price,
    )
    # Remaining lot 1: 50 units
    # Lot 1 unrealized: 50 * (100 - 50) = 2500
    # Lot 2 unrealized: 200 * (100 - 80) = 4000
    # Total = 6500
    assert tracker.unrealized_gains(date(2024, 1, 1), current_price) == Decimal("6500")


# ---------------------------------------------------------------------------
# test 11: no float annotations in the module
# ---------------------------------------------------------------------------


def test_no_float_in_module() -> None:
    """AST scan of tax_engine.py must find zero ': float' type annotations."""
    module_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "backend",
        "services",
        "simulation",
        "tax_engine.py",
    )
    module_path = os.path.normpath(module_path)
    assert os.path.exists(module_path), f"Module not found: {module_path}"
    assert not _has_float_annotation(module_path), (
        "tax_engine.py contains ': float' annotations — violates Decimal-not-float law"
    )


# ---------------------------------------------------------------------------
# test 12: mixed lots partial sell
# ---------------------------------------------------------------------------


def test_mixed_lots_partial_sell() -> None:
    """Buy 3 lots. Sell 250 units. Verify FIFO consumption and correct per-lot tax."""
    # Lot A: 100 units @ ₹50 (2022-01-01) — LTCG when sold 2024-07-24
    # Lot B: 100 units @ ₹80 (2023-01-01) — LTCG when sold 2024-07-24
    # Lot C: 100 units @ ₹90 (2024-06-01) — STCG when sold 2024-07-24
    tracker = _make_tracker(
        (date(2022, 1, 1), Decimal("100"), Decimal("50")),
        (date(2023, 1, 1), Decimal("100"), Decimal("80")),
        (date(2024, 6, 1), Decimal("100"), Decimal("90")),
    )

    disposals = tracker.sell_units(
        sell_date=date(2024, 7, 24),
        units_to_sell=Decimal("250"),
        sell_price_per_unit=Decimal("120"),
    )

    assert len(disposals) == 3

    # Lot A: 100 units, LTCG (sold post-budget)
    da = disposals[0]
    assert da.units_sold == Decimal("100")
    assert da.lot.buy_date == date(2022, 1, 1)
    assert da.is_ltcg
    # gain = 100 * (120 - 50) = 7000; LTCG tax = 7000 * 0.125 = 875
    assert da.gain == Decimal("7000")
    assert da.tax_detail.ltcg_tax == Decimal("875")

    # Lot B: 100 units, LTCG (post-budget)
    db = disposals[1]
    assert db.units_sold == Decimal("100")
    assert db.is_ltcg
    # gain = 100 * (120 - 80) = 4000; LTCG tax = 4000 * 0.125 = 500
    assert db.gain == Decimal("4000")
    assert db.tax_detail.ltcg_tax == Decimal("500")

    # Lot C: 50 units (partial), STCG (post-budget, only ~53 days held)
    dc = disposals[2]
    assert dc.units_sold == Decimal("50")
    assert not dc.is_ltcg
    # gain = 50 * (120 - 90) = 1500; STCG tax = 1500 * 0.20 = 300
    assert dc.gain == Decimal("1500")
    assert dc.tax_detail.stcg_tax == Decimal("300")

    # 50 units of lot C remain
    assert tracker.total_units == Decimal("50")
    assert tracker.lots[0].buy_date == date(2024, 6, 1)
    assert tracker.lots[0].remaining_units == Decimal("50")


# ---------------------------------------------------------------------------
# test 13: sell more than held raises ValueError
# ---------------------------------------------------------------------------


def test_sell_more_than_available_raises() -> None:
    """Attempting to sell more units than held raises ValueError."""
    tracker = _make_tracker(
        (date(2024, 1, 1), Decimal("100"), Decimal("50")),
    )
    with pytest.raises(ValueError, match="Cannot sell"):
        tracker.sell_units(
            sell_date=date(2024, 12, 1),
            units_to_sell=Decimal("101"),
            sell_price_per_unit=Decimal("60"),
        )


# ---------------------------------------------------------------------------
# test 14: determinism — same computation twice gives identical results
# ---------------------------------------------------------------------------


def test_deterministic() -> None:
    """Same inputs must produce identical outputs (System Guarantee #1)."""

    def _run() -> tuple[Decimal, Decimal, Decimal]:
        tracker = _make_tracker(
            (date(2022, 6, 1), Decimal("500"), Decimal("100")),
            (date(2023, 6, 1), Decimal("300"), Decimal("150")),
        )
        disposals = tracker.sell_units(
            sell_date=date(2024, 9, 1),
            units_to_sell=Decimal("600"),
            sell_price_per_unit=Decimal("250"),
        )
        summary = compute_annual_tax_summary(
            disposals=disposals,
            financial_year_start=date(2024, 4, 1),
        )
        return summary.stcg, summary.ltcg, summary.total_tax

    run1 = _run()
    run2 = _run()
    assert run1 == run2, f"Non-deterministic! run1={run1}, run2={run2}"
