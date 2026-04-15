"""Unit tests for portfolio tax harvesting service.

Tests:
- tax_harvest.py imports from backend.services.simulation.tax_engine (AST check)
- tax_harvest.py contains NO rate tables, NO cess constants, NO FIFO logic (grep/AST)
- Bit-for-bit match: same lots as V3 FIFO golden fixture → same unrealized loss
- Holding with unrealized gain produces no opportunity
- Holding with unrealized loss produces correct STCG/LTCG saving calculation
- Mixed lots (some profitable, some losing) only flags losing lots
- Empty holdings produces empty summary
- Deterministic: same data_as_of → same output
"""

from __future__ import annotations

import ast
import datetime
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from backend.services.portfolio.tax_harvest import identify_harvest_opportunities
from backend.services.simulation.tax_engine import (
    FIFOLotTracker,
    IndianTaxRates,
)


# ---------------------------------------------------------------------------
# Path to the source file under test
# ---------------------------------------------------------------------------

_TAX_HARVEST_PATH = Path(__file__).parent.parent.parent.parent / (
    "backend/services/portfolio/tax_harvest.py"
)


# ---------------------------------------------------------------------------
# AST / static analysis checks
# ---------------------------------------------------------------------------


def test_tax_harvest_imports_from_tax_engine() -> None:
    """tax_harvest.py must import from backend.services.simulation.tax_engine."""
    source = _TAX_HARVEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    tax_engine_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "tax_engine" in node.module:
                tax_engine_imports.append(node.module)

    assert len(tax_engine_imports) > 0, (
        "tax_harvest.py must import from backend.services.simulation.tax_engine"
    )
    assert any("simulation.tax_engine" in m for m in tax_engine_imports)


def test_tax_harvest_contains_no_rate_tables() -> None:
    """tax_harvest.py must NOT define rate tables (dicts mapping to Decimal rates)."""
    source = _TAX_HARVEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Check for any assignment of float/Decimal literals that look like tax rates
    # Rate tables would contain values like 0.15, 0.20, 0.125, 0.10
    forbidden_rate_values = {"0.15", "0.20", "0.125", "0.10"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in forbidden_rate_values:
                pytest.fail(
                    f"tax_harvest.py contains hardcoded rate value '{node.value}' — "
                    "rates must come from IndianTaxRates in tax_engine.py"
                )


def test_tax_harvest_contains_no_cess_constant() -> None:
    """tax_harvest.py must NOT define CESS_RATE or cess constant."""
    source = _TAX_HARVEST_PATH.read_text(encoding="utf-8")

    # Check for any assignment of CESS constants
    assert "CESS_RATE" not in source or "rates.CESS_RATE" in source, (
        "tax_harvest.py must not define CESS_RATE — use rates.CESS_RATE from tax_engine"
    )

    # More specific: should not have a line assigning CESS_RATE = ...
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("CESS_RATE") and "=" in stripped and "rates." not in stripped:
            pytest.fail(f"tax_harvest.py has hardcoded CESS_RATE assignment: {stripped!r}")


def test_tax_harvest_contains_no_fifo_logic() -> None:
    """tax_harvest.py must NOT contain FIFO deque/pop/popleft logic."""
    source = _TAX_HARVEST_PATH.read_text(encoding="utf-8")

    # FIFOLotTracker usage is fine (import + instantiation)
    # but the module must not RE-IMPLEMENT FIFO via deque
    forbidden_patterns = ["deque()", "popleft()", "collections.deque"]
    for pattern in forbidden_patterns:
        assert pattern not in source, (
            f"tax_harvest.py contains FIFO implementation pattern '{pattern}' — "
            "FIFO logic must live only in tax_engine.py"
        )


def test_tax_harvest_no_float_annotations() -> None:
    """tax_harvest.py must not use float type annotations."""
    from backend.services.simulation.tax_engine import _has_float_annotation

    assert not _has_float_annotation(str(_TAX_HARVEST_PATH)), (
        "tax_harvest.py contains float type annotations — use Decimal instead"
    )


# ---------------------------------------------------------------------------
# Golden fixture: bit-for-bit match with V3 FIFO engine
# ---------------------------------------------------------------------------


def test_bit_for_bit_match_with_fifo_golden_fixture() -> None:
    """Verify identify_harvest_opportunities uses FIFOLotTracker unrealized losses correctly.

    Golden fixture: 100 units bought at ₹200 on 2024-01-02.
    Current price: ₹180. Unrealized loss = (180 - 200) × 100 = -₹2,000.

    Verify: identify_harvest_opportunities returns the same loss figure as
    FIFOLotTracker.unrealized_gains() directly.
    """
    buy_date = datetime.date(2024, 1, 2)
    units = Decimal("100")
    cost_per_unit = Decimal("200")
    current_price = Decimal("180")
    data_as_of = datetime.date(2025, 4, 15)

    # Direct FIFO engine computation (ground truth)
    tracker = FIFOLotTracker()
    tracker.add_lot(buy_date=buy_date, units=units, cost_per_unit=cost_per_unit)
    direct_unrealized_gain = tracker.unrealized_gains(
        current_date=data_as_of, current_price=current_price
    )
    assert direct_unrealized_gain == Decimal("-2000"), (
        f"Expected -2000, got {direct_unrealized_gain}"
    )

    # identify_harvest_opportunities should find same loss
    holding_id = uuid.uuid4()
    holdings_with_lots = [
        {
            "holding_id": holding_id,
            "mstar_id": "F00000GOLDEN",
            "scheme_name": "Golden Fixture Fund",
            "lots": [
                {
                    "buy_date": buy_date,
                    "units": units,
                    "cost_per_unit": cost_per_unit,
                }
            ],
        }
    ]
    current_prices = {"F00000GOLDEN": current_price}

    summary = identify_harvest_opportunities(holdings_with_lots, current_prices, data_as_of)

    assert len(summary.opportunities) == 1
    opp = summary.opportunities[0]
    # Bit-for-bit match: unrealized_loss must equal abs(direct_unrealized_gain)
    assert opp.unrealized_loss == abs(direct_unrealized_gain), (
        f"Expected unrealized_loss={abs(direct_unrealized_gain)}, got {opp.unrealized_loss}"
    )


# ---------------------------------------------------------------------------
# Business logic tests
# ---------------------------------------------------------------------------


def test_holding_with_unrealized_gain_produces_no_opportunity() -> None:
    buy_date = datetime.date(2024, 1, 2)
    current_price = Decimal("250")  # bought at 200, now 250 = gain
    data_as_of = datetime.date(2025, 4, 15)

    holdings_with_lots = [
        {
            "holding_id": uuid.uuid4(),
            "mstar_id": "F00000GAIN",
            "scheme_name": "Profitable Fund",
            "lots": [
                {
                    "buy_date": buy_date,
                    "units": Decimal("100"),
                    "cost_per_unit": Decimal("200"),
                }
            ],
        }
    ]
    current_prices = {"F00000GAIN": current_price}

    summary = identify_harvest_opportunities(holdings_with_lots, current_prices, data_as_of)

    assert len(summary.opportunities) == 0
    assert summary.total_harvestable_loss == Decimal("0")
    assert summary.total_potential_saving == Decimal("0")


def test_stcg_loss_produces_correct_saving() -> None:
    """STCG loss: bought 2025-01-01, selling 2025-04-15 = 104 days (STCG, <365).
    Loss = (160 - 200) × 100 = -₹4,000.
    Rate (post 2024-07-23): stcg=20%, cess=4%.
    Expected saving = 4000 × 0.20 × 1.04 = ₹832.
    """
    buy_date = datetime.date(2025, 1, 1)
    current_price = Decimal("160")
    cost_per_unit = Decimal("200")
    units = Decimal("100")
    data_as_of = datetime.date(2025, 4, 15)  # Post-budget → stcg=20%

    holdings_with_lots = [
        {
            "holding_id": uuid.uuid4(),
            "mstar_id": "F00000STCG",
            "scheme_name": "STCG Loss Fund",
            "lots": [
                {
                    "buy_date": buy_date,
                    "units": units,
                    "cost_per_unit": cost_per_unit,
                }
            ],
        }
    ]
    current_prices = {"F00000STCG": current_price}

    summary = identify_harvest_opportunities(holdings_with_lots, current_prices, data_as_of)

    assert len(summary.opportunities) == 1
    opp = summary.opportunities[0]

    expected_loss = Decimal("4000")
    assert opp.unrealized_loss == expected_loss

    rates = IndianTaxRates.get_rates(data_as_of)
    expected_stcg_saving = expected_loss * rates.stcg_rate * (Decimal("1") + rates.CESS_RATE)
    assert opp.potential_stcg_saving == expected_stcg_saving
    assert opp.potential_ltcg_saving == Decimal("0")


def test_ltcg_loss_produces_correct_saving() -> None:
    """LTCG loss: bought 2023-01-01, selling 2025-04-15 = >365 days (LTCG).
    Loss = (180 - 200) × 100 = -₹2,000.
    Rate (post 2024-07-23): ltcg=12.5%, cess=4%.
    Expected saving = 2000 × 0.125 × 1.04 = ₹260.
    """
    buy_date = datetime.date(2023, 1, 1)
    current_price = Decimal("180")
    cost_per_unit = Decimal("200")
    units = Decimal("100")
    data_as_of = datetime.date(2025, 4, 15)

    holdings_with_lots = [
        {
            "holding_id": uuid.uuid4(),
            "mstar_id": "F00000LTCG",
            "scheme_name": "LTCG Loss Fund",
            "lots": [
                {
                    "buy_date": buy_date,
                    "units": units,
                    "cost_per_unit": cost_per_unit,
                }
            ],
        }
    ]
    current_prices = {"F00000LTCG": current_price}

    summary = identify_harvest_opportunities(holdings_with_lots, current_prices, data_as_of)

    assert len(summary.opportunities) == 1
    opp = summary.opportunities[0]

    expected_loss = Decimal("2000")
    assert opp.unrealized_loss == expected_loss

    rates = IndianTaxRates.get_rates(data_as_of)
    expected_ltcg_saving = expected_loss * rates.ltcg_rate * (Decimal("1") + rates.CESS_RATE)
    assert opp.potential_ltcg_saving == expected_ltcg_saving
    assert opp.potential_stcg_saving == Decimal("0")


def test_mixed_lots_only_flags_losing_lots() -> None:
    """One profitable lot + one losing lot: only the losing lot contributes."""
    holding_id = uuid.uuid4()
    data_as_of = datetime.date(2025, 4, 15)

    holdings_with_lots = [
        {
            "holding_id": holding_id,
            "mstar_id": "F00000MIXED",
            "scheme_name": "Mixed Fund",
            "lots": [
                # Profitable lot: bought at 100, current 150 = +50/unit
                {
                    "buy_date": datetime.date(2025, 1, 1),
                    "units": Decimal("100"),
                    "cost_per_unit": Decimal("100"),
                },
                # Losing lot: bought at 200, current 150 = -50/unit
                {
                    "buy_date": datetime.date(2024, 6, 1),
                    "units": Decimal("50"),
                    "cost_per_unit": Decimal("200"),
                },
            ],
        }
    ]
    current_prices = {"F00000MIXED": Decimal("150")}

    summary = identify_harvest_opportunities(holdings_with_lots, current_prices, data_as_of)

    assert len(summary.opportunities) == 1
    opp = summary.opportunities[0]

    # Only the losing lot contributes: -50 × 50 = -2500 loss
    assert opp.unrealized_loss == Decimal("2500")
    assert len(opp.lots) == 1  # Only the losing lot is in the details
    assert opp.lots[0].cost_per_unit == Decimal("200")


def test_empty_holdings_produces_empty_summary() -> None:
    data_as_of = datetime.date(2025, 4, 15)
    summary = identify_harvest_opportunities([], {}, data_as_of)

    assert len(summary.opportunities) == 0
    assert summary.total_harvestable_loss == Decimal("0")
    assert summary.total_potential_saving == Decimal("0")
    assert summary.data_as_of == data_as_of


def test_missing_price_skips_holding_gracefully() -> None:
    """When current_prices doesn't contain the mstar_id, holding is skipped (no crash)."""
    data_as_of = datetime.date(2025, 4, 15)
    holdings_with_lots = [
        {
            "holding_id": uuid.uuid4(),
            "mstar_id": "F00000NOPRICE",
            "scheme_name": "No Price Fund",
            "lots": [
                {
                    "buy_date": datetime.date(2025, 1, 1),
                    "units": Decimal("100"),
                    "cost_per_unit": Decimal("200"),
                }
            ],
        }
    ]
    # Missing price for F00000NOPRICE
    summary = identify_harvest_opportunities(holdings_with_lots, {}, data_as_of)
    assert len(summary.opportunities) == 0


def test_opportunities_sorted_by_potential_saving_descending() -> None:
    """Multiple holdings: sorted by largest saving first."""
    data_as_of = datetime.date(2025, 4, 15)

    holdings_with_lots = [
        {
            "holding_id": uuid.uuid4(),
            "mstar_id": "F00000SMALL",
            "scheme_name": "Small Loss Fund",
            "lots": [
                {
                    "buy_date": datetime.date(2025, 1, 1),
                    "units": Decimal("10"),
                    "cost_per_unit": Decimal("200"),
                }
            ],
        },
        {
            "holding_id": uuid.uuid4(),
            "mstar_id": "F00000LARGE",
            "scheme_name": "Large Loss Fund",
            "lots": [
                {
                    "buy_date": datetime.date(2025, 1, 1),
                    "units": Decimal("1000"),
                    "cost_per_unit": Decimal("200"),
                }
            ],
        },
    ]
    current_prices = {
        "F00000SMALL": Decimal("150"),  # -50 × 10 = -500 loss
        "F00000LARGE": Decimal("150"),  # -50 × 1000 = -50000 loss
    }

    summary = identify_harvest_opportunities(holdings_with_lots, current_prices, data_as_of)

    assert len(summary.opportunities) == 2
    # Largest loss first
    assert summary.opportunities[0].scheme_name == "Large Loss Fund"
    assert summary.opportunities[1].scheme_name == "Small Loss Fund"


def test_deterministic_same_data_as_of_same_output() -> None:
    """Same inputs → same TaxHarvestSummary (deterministic)."""
    data_as_of = datetime.date(2025, 4, 15)
    holding_id = uuid.uuid4()

    holdings_with_lots = [
        {
            "holding_id": holding_id,
            "mstar_id": "F00000DET",
            "scheme_name": "Deterministic Fund",
            "lots": [
                {
                    "buy_date": datetime.date(2025, 1, 1),
                    "units": Decimal("100"),
                    "cost_per_unit": Decimal("200"),
                }
            ],
        }
    ]
    current_prices = {"F00000DET": Decimal("150")}

    summary1 = identify_harvest_opportunities(holdings_with_lots, current_prices, data_as_of)
    summary2 = identify_harvest_opportunities(holdings_with_lots, current_prices, data_as_of)

    assert len(summary1.opportunities) == len(summary2.opportunities)
    assert summary1.total_harvestable_loss == summary2.total_harvestable_loss
    assert summary1.total_potential_saving == summary2.total_potential_saving
    assert summary1.opportunities[0].unrealized_loss == summary2.opportunities[0].unrealized_loss
    assert (
        summary1.opportunities[0].potential_stcg_saving
        == summary2.opportunities[0].potential_stcg_saving
    )
