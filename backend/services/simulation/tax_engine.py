"""Indian FIFO Capital Gains Tax Engine — pure computation module.

No DB, no I/O, no async. Implements spec §8 tax rules:

Pre 23-Jul-2024:
    STCG: 15% | LTCG: 10% | Exemption: ₹1,00,000
Post 23-Jul-2024:
    STCG: 20% | LTCG: 12.5% | Exemption: ₹1,25,000

4% Health & Education Cess on all tax.
FIFO lot tracking: sell oldest units first.
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import ClassVar

from backend.models.simulation import TaxDetail, TaxSummary


# ---------------------------------------------------------------------------
# Constants / Regime config
# ---------------------------------------------------------------------------

_BUDGET_2024_CUTOFF: date = date(2024, 7, 23)
_LTCG_HOLDING_DAYS: int = 365  # >12 months = >365 days


@dataclass(frozen=True)
class IndianTaxRates:
    """Immutable tax rate configuration for one budget regime.

    Class-level singletons PRE_BUDGET_2024 and POST_BUDGET_2024 are set after
    the class definition to avoid forward-reference issues.
    """

    stcg_rate: Decimal
    ltcg_rate: Decimal
    ltcg_exemption: Decimal  # Annual aggregate exemption in INR
    regime_name: str

    # Instance constants — not constructor params
    CESS_RATE: Decimal = field(default=Decimal("0.04"), init=False)
    LTCG_HOLDING_MONTHS: int = field(default=12, init=False)

    # Class-level regime singletons — ClassVar so dataclass ignores them
    PRE_BUDGET_2024: ClassVar["IndianTaxRates"]
    POST_BUDGET_2024: ClassVar["IndianTaxRates"]

    @staticmethod
    def get_rates(sell_date: date) -> "IndianTaxRates":
        """Return the applicable tax regime for a given sell date."""
        if sell_date >= _BUDGET_2024_CUTOFF:
            return IndianTaxRates.POST_BUDGET_2024
        return IndianTaxRates.PRE_BUDGET_2024


# Singleton instances — defined after the class to allow forward reference
IndianTaxRates.PRE_BUDGET_2024 = IndianTaxRates(
    stcg_rate=Decimal("0.15"),
    ltcg_rate=Decimal("0.10"),
    ltcg_exemption=Decimal("100000"),
    regime_name="PRE_BUDGET_2024",
)

IndianTaxRates.POST_BUDGET_2024 = IndianTaxRates(
    stcg_rate=Decimal("0.20"),
    ltcg_rate=Decimal("0.125"),
    ltcg_exemption=Decimal("125000"),
    regime_name="POST_BUDGET_2024",
)

# Module-level aliases for convenience
_PRE_BUDGET_2024 = IndianTaxRates.PRE_BUDGET_2024
_POST_BUDGET_2024 = IndianTaxRates.POST_BUDGET_2024


# ---------------------------------------------------------------------------
# TaxLot — represents one purchase lot
# ---------------------------------------------------------------------------


@dataclass
class TaxLot:
    """A single purchase lot for FIFO tracking."""

    buy_date: date
    units: Decimal
    cost_per_unit: Decimal
    remaining_units: Decimal = field(init=False)

    def __post_init__(self) -> None:
        self.remaining_units = self.units


# ---------------------------------------------------------------------------
# LotDisposal — result of consuming (part of) a lot in a sell
# ---------------------------------------------------------------------------


@dataclass
class LotDisposal:
    """Per-lot disposal result from a sell event."""

    lot: TaxLot
    units_sold: Decimal
    sell_price_per_unit: Decimal
    sell_date: date

    # Derived — populated in __post_init__
    cost_basis: Decimal = field(init=False)
    proceeds: Decimal = field(init=False)
    gain: Decimal = field(init=False)
    holding_days: int = field(init=False)
    is_ltcg: bool = field(init=False)
    tax_detail: TaxDetail = field(init=False)

    def __post_init__(self) -> None:
        self.cost_basis = self.units_sold * self.lot.cost_per_unit
        self.proceeds = self.units_sold * self.sell_price_per_unit
        self.gain = self.proceeds - self.cost_basis
        self.holding_days = (self.sell_date - self.lot.buy_date).days
        self.is_ltcg = self.holding_days > _LTCG_HOLDING_DAYS
        # Compute tax using the regime applicable to the sell date
        rates = IndianTaxRates.get_rates(self.sell_date)
        self.tax_detail = compute_tax_on_disposal(self, rates)


# ---------------------------------------------------------------------------
# FIFOLotTracker — manages the lot queue
# ---------------------------------------------------------------------------


class FIFOLotTracker:
    """FIFO queue of purchase lots. Sells consume the oldest lots first."""

    def __init__(self) -> None:
        self._lots: deque[TaxLot] = deque()

    def add_lot(
        self,
        buy_date: date,
        units: Decimal,
        cost_per_unit: Decimal,
    ) -> None:
        """Append a new purchase lot to the back of the queue."""
        lot = TaxLot(
            buy_date=buy_date,
            units=units,
            cost_per_unit=cost_per_unit,
        )
        self._lots.append(lot)

    def sell_units(
        self,
        sell_date: date,
        units_to_sell: Decimal,
        sell_price_per_unit: Decimal,
    ) -> list[LotDisposal]:
        """Consume units FIFO and return a LotDisposal per lot touched.

        Raises ValueError if units_to_sell exceeds total held.
        """
        total_held: Decimal = sum((lot.remaining_units for lot in self._lots), Decimal("0"))
        if units_to_sell > total_held:
            raise ValueError(f"Cannot sell {units_to_sell} units; only {total_held} held.")

        disposals: list[LotDisposal] = []
        remaining_to_sell = units_to_sell

        while remaining_to_sell > Decimal("0") and self._lots:
            lot = self._lots[0]
            units_from_this_lot = min(lot.remaining_units, remaining_to_sell)

            disposal = LotDisposal(
                lot=lot,
                units_sold=units_from_this_lot,
                sell_price_per_unit=sell_price_per_unit,
                sell_date=sell_date,
            )
            disposals.append(disposal)

            lot.remaining_units -= units_from_this_lot
            remaining_to_sell -= units_from_this_lot

            # Remove exhausted lot
            if lot.remaining_units == Decimal("0"):
                self._lots.popleft()

        return disposals

    def unrealized_gains(
        self,
        current_date: date,
        current_price: Decimal,
    ) -> Decimal:
        """Sum of unrealized gains on all remaining lots at current_price."""
        total: Decimal = Decimal("0")
        for lot in self._lots:
            market_value = lot.remaining_units * current_price
            cost = lot.remaining_units * lot.cost_per_unit
            total += market_value - cost
        return total

    @property
    def total_units(self) -> Decimal:
        """Total units currently held across all lots."""
        return sum((lot.remaining_units for lot in self._lots), Decimal("0"))

    @property
    def lots(self) -> list[TaxLot]:
        """Read-only view of current lots (oldest first)."""
        return list(self._lots)


# ---------------------------------------------------------------------------
# compute_tax_on_disposal — per-transaction tax (no exemption applied)
# ---------------------------------------------------------------------------


def compute_tax_on_disposal(
    disposal: LotDisposal,
    rates: IndianTaxRates,
) -> TaxDetail:
    """Compute tax on a single lot disposal.

    LTCG exemption is NOT applied here — it is applied at annual aggregate level
    in compute_annual_tax_summary. This function returns the full unexempted tax.

    If gain <= 0, returns a zero TaxDetail.
    """
    if disposal.gain <= Decimal("0"):
        return TaxDetail(
            stcg_tax=Decimal("0"),
            ltcg_tax=Decimal("0"),
            cess=Decimal("0"),
            total_tax=Decimal("0"),
        )

    stcg_tax = Decimal("0")
    ltcg_tax = Decimal("0")

    if disposal.is_ltcg:
        ltcg_tax = disposal.gain * rates.ltcg_rate
    else:
        stcg_tax = disposal.gain * rates.stcg_rate

    gross_tax = stcg_tax + ltcg_tax
    cess = gross_tax * rates.CESS_RATE
    total_tax = gross_tax + cess

    return TaxDetail(
        stcg_tax=stcg_tax,
        ltcg_tax=ltcg_tax,
        cess=cess,
        total_tax=total_tax,
    )


# ---------------------------------------------------------------------------
# compute_annual_tax_summary — aggregate across all disposals in one FY
# ---------------------------------------------------------------------------


def _financial_year_of(d: date) -> int:
    """Return the starting calendar year of the Indian financial year for date d.

    FY2024-25 starts 2024-04-01; dates Jan–Mar 2025 → FY starting 2024.
    """
    if d.month >= 4:
        return d.year
    return d.year - 1


def compute_annual_tax_summary(
    disposals: list[LotDisposal],
    financial_year_start: date,
) -> TaxSummary:
    """Compute aggregate tax for a single financial year.

    Groups disposals by FY of sell_date, selects those matching financial_year_start.
    Applies LTCG exemption (₹1L or ₹1.25L) to aggregate LTCG gains.
    post_tax_xirr and unrealized are set to Decimal("0") — computed by caller.

    Args:
        disposals: All LotDisposal objects from the simulation.
        financial_year_start: date(YYYY, 4, 1) for the target FY.
    """
    target_fy = _financial_year_of(financial_year_start)

    # Filter disposals belonging to this FY
    fy_disposals = [d for d in disposals if _financial_year_of(d.sell_date) == target_fy]

    if not fy_disposals:
        return TaxSummary(
            stcg=Decimal("0"),
            ltcg=Decimal("0"),
            total_tax=Decimal("0"),
            post_tax_xirr=Decimal("0"),
            unrealized=Decimal("0"),
        )

    # Aggregate gains
    total_stcg_gain = Decimal("0")
    total_ltcg_gain = Decimal("0")

    # Use the regime of the last sell date in the FY to pick exemption.
    # (More than one regime can be active in an FY if crossing 23-Jul-2024.
    # Conservative approach: use POST if any sell is post-budget.)
    latest_sell_date = max(d.sell_date for d in fy_disposals)
    rates = IndianTaxRates.get_rates(latest_sell_date)

    for d in fy_disposals:
        if d.gain <= Decimal("0"):
            continue  # Losses don't offset gains in simple model
        if d.is_ltcg:
            total_ltcg_gain += d.gain
        else:
            total_stcg_gain += d.gain

    # Apply LTCG exemption
    taxable_ltcg = max(total_ltcg_gain - rates.ltcg_exemption, Decimal("0"))
    taxable_stcg = total_stcg_gain

    stcg_tax = taxable_stcg * rates.stcg_rate
    ltcg_tax = taxable_ltcg * rates.ltcg_rate

    gross_tax = stcg_tax + ltcg_tax
    cess = gross_tax * rates.CESS_RATE
    total_tax = gross_tax + cess

    return TaxSummary(
        stcg=total_stcg_gain,
        ltcg=total_ltcg_gain,
        total_tax=total_tax,
        post_tax_xirr=Decimal("0"),
        unrealized=Decimal("0"),
    )


# ---------------------------------------------------------------------------
# Utility: AST scan for float annotations (used in tests)
# ---------------------------------------------------------------------------


def _has_float_annotation(source_path: str) -> bool:
    """Return True if the source file contains any bare-float type annotation."""
    with open(source_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)

    for node in ast.walk(tree):
        # Function argument annotations
        if isinstance(node, ast.arg) and node.annotation is not None:
            ann = node.annotation
            if isinstance(ann, ast.Name) and ann.id == "float":
                return True
        # Function return annotations
        if isinstance(node, ast.FunctionDef) and node.returns is not None:
            ret = node.returns
            if isinstance(ret, ast.Name) and ret.id == "float":
                return True
        # Variable annotations (e.g. bare-float annotated assignments)
        if isinstance(node, ast.AnnAssign) and node.annotation is not None:
            ann = node.annotation
            if isinstance(ann, ast.Name) and ann.id == "float":
                return True

    return False


__all__ = [
    "TaxLot",
    "LotDisposal",
    "FIFOLotTracker",
    "IndianTaxRates",
    "compute_tax_on_disposal",
    "compute_annual_tax_summary",
    "_has_float_annotation",
    "_PRE_BUDGET_2024",
    "_POST_BUDGET_2024",
]
