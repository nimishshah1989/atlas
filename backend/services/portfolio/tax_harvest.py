"""Tax Harvesting Opportunities — thin wrapper over V3 FIFO tax engine.

This module identifies holdings with unrealized losses that could offset
realized gains for tax purposes.

Design contract:
  - NO rate tables in this module
  - NO cess constants in this module
  - NO FIFO logic in this module
  - All rate lookups delegated to backend.services.simulation.tax_engine.IndianTaxRates
  - All lot tracking delegated to backend.services.simulation.tax_engine.FIFOLotTracker
  - All financial arithmetic in Decimal, never float
  - Deterministic: same inputs → same TaxHarvestSummary
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

import structlog

from backend.models.portfolio import AnalysisProvenance
from backend.models.portfolio_monitoring import (
    TaxHarvestLot,
    TaxHarvestOpportunity,
    TaxHarvestSummary,
)
from backend.services.simulation.tax_engine import (
    FIFOLotTracker,
    IndianTaxRates,
    TaxLot,
)

log = structlog.get_logger()

# LTCG holding threshold — imported implicitly from tax_engine via IndianTaxRates
_LTCG_HOLDING_DAYS: int = 365  # >12 months = >365 days (mirrors tax_engine constant)


def _lot_unrealized_gain(
    lot: TaxLot,
    current_price: Decimal,
) -> Decimal:
    """Compute unrealized gain for a single lot (negative = loss).

    Delegates no business logic — purely: (current_price - cost_per_unit) * remaining_units.
    """
    return (current_price - lot.cost_per_unit) * lot.remaining_units


def _lot_potential_saving(
    lot: TaxLot,
    current_price: Decimal,
    current_date: datetime.date,
    rates: IndianTaxRates,
) -> tuple[Decimal, Decimal]:
    """Compute potential STCG and LTCG tax saving if this loss lot is harvested.

    Returns (potential_stcg_saving, potential_ltcg_saving).  Both are >= 0.
    If the lot has a gain (not a loss), returns (0, 0).
    """
    gain = _lot_unrealized_gain(lot, current_price)
    if gain >= Decimal("0"):
        return Decimal("0"), Decimal("0")

    loss = abs(gain)
    holding_days = (current_date - lot.buy_date).days
    is_ltcg = holding_days > _LTCG_HOLDING_DAYS

    if is_ltcg:
        # LTCG saving: loss × ltcg_rate × (1 + cess_rate)
        raw_saving = loss * rates.ltcg_rate * (Decimal("1") + rates.CESS_RATE)
        return Decimal("0"), raw_saving
    else:
        # STCG saving: loss × stcg_rate × (1 + cess_rate)
        raw_saving = loss * rates.stcg_rate * (Decimal("1") + rates.CESS_RATE)
        return raw_saving, Decimal("0")


def identify_harvest_opportunities(
    holdings_with_lots: list[dict[str, Any]],
    current_prices: dict[str, Decimal],
    data_as_of: datetime.date,
) -> TaxHarvestSummary:
    """Identify tax loss harvesting opportunities across a portfolio.

    Args:
        holdings_with_lots: List of dicts, each with keys:
            - holding_id (str | UUID): portfolio holding identifier
            - mstar_id (str): Morningstar fund identifier
            - scheme_name (str): Display name of the fund
            - lots (list[dict]): Each lot dict has keys:
                - buy_date (datetime.date)
                - units (Decimal)
                - cost_per_unit (Decimal)
        current_prices: Dict of mstar_id → current NAV (Decimal).
        data_as_of: Reference date for rate regime selection and holding day calculation.

    Returns:
        TaxHarvestSummary with opportunities sorted by total_potential_saving descending.
    """
    computed_at = datetime.datetime.now(datetime.timezone.utc)
    # Rate regime from tax_engine — all rate knowledge lives there
    rates = IndianTaxRates.get_rates(data_as_of)

    opportunities: list[TaxHarvestOpportunity] = []

    for holding in holdings_with_lots:
        holding_id = str(holding["holding_id"])
        mstar_id = str(holding["mstar_id"])
        scheme_name = str(holding["scheme_name"])
        raw_lots: list[dict[str, Any]] = holding.get("lots", [])

        current_price = current_prices.get(mstar_id)
        if current_price is None:
            log.warning(
                "tax_harvest_no_price",
                holding_id=holding_id,
                mstar_id=mstar_id,
            )
            continue

        # Reconstruct FIFOLotTracker to reuse lot data
        tracker = FIFOLotTracker()
        for raw_lot in raw_lots:
            tracker.add_lot(
                buy_date=raw_lot["buy_date"],
                units=Decimal(str(raw_lot["units"])),
                cost_per_unit=Decimal(str(raw_lot["cost_per_unit"])),
            )

        # Compute per-lot details
        lot_details: list[TaxHarvestLot] = []
        total_stcg_saving = Decimal("0")
        total_ltcg_saving = Decimal("0")
        total_loss = Decimal("0")

        for lot in tracker.lots:
            gain = _lot_unrealized_gain(lot, current_price)
            if gain >= Decimal("0"):
                # Profitable lot — skip for harvesting purposes
                continue

            loss = abs(gain)
            holding_days = (data_as_of - lot.buy_date).days
            is_ltcg = holding_days > _LTCG_HOLDING_DAYS

            stcg_saving, ltcg_saving = _lot_potential_saving(lot, current_price, data_as_of, rates)
            lot_saving = stcg_saving + ltcg_saving

            lot_details.append(
                TaxHarvestLot(
                    buy_date=lot.buy_date,
                    units=lot.remaining_units,
                    cost_per_unit=lot.cost_per_unit,
                    current_price=current_price,
                    unrealized_gain=gain,
                    holding_days=holding_days,
                    is_ltcg=is_ltcg,
                    potential_saving=lot_saving,
                )
            )

            total_loss += loss
            total_stcg_saving += stcg_saving
            total_ltcg_saving += ltcg_saving

        if not lot_details:
            # No losing lots for this holding
            continue

        total_saving = total_stcg_saving + total_ltcg_saving

        log.info(
            "tax_harvest_opportunity",
            mstar_id=mstar_id,
            total_loss=str(total_loss),
            total_saving=str(total_saving),
            lot_count=len(lot_details),
        )

        opportunities.append(
            TaxHarvestOpportunity(
                holding_id=holding["holding_id"],
                mstar_id=mstar_id,
                scheme_name=scheme_name,
                unrealized_loss=total_loss,
                potential_stcg_saving=total_stcg_saving,
                potential_ltcg_saving=total_ltcg_saving,
                total_potential_saving=total_saving,
                lots=lot_details,
                provenance=AnalysisProvenance(
                    source_table=(
                        "FIFOLotTracker (backend.services.simulation.tax_engine) "
                        "/ IndianTaxRates.get_rates(data_as_of)"
                    ),
                    formula=(
                        f"loss × rate × (1 + cess_rate); regime={rates.regime_name}; "
                        f"stcg_rate={rates.stcg_rate}; ltcg_rate={rates.ltcg_rate}; "
                        f"cess_rate={rates.CESS_RATE}"
                    ),
                ),
            )
        )

    # Sort by total potential saving descending (largest benefit first)
    opportunities.sort(key=lambda o: o.total_potential_saving, reverse=True)

    total_harvestable_loss = sum((o.unrealized_loss for o in opportunities), Decimal("0"))
    total_potential_saving = sum((o.total_potential_saving for o in opportunities), Decimal("0"))

    return TaxHarvestSummary(
        opportunities=opportunities,
        total_harvestable_loss=total_harvestable_loss,
        total_potential_saving=total_potential_saving,
        data_as_of=data_as_of,
        computed_at=computed_at,
    )


__all__ = [
    "identify_harvest_opportunities",
]
