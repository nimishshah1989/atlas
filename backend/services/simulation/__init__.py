"""V3 Simulation Engine — foundation package."""

from backend.services.simulation.service import SimulationService
from backend.services.simulation.signal_adapters import (
    SignalPoint,
    SignalSeries,
    SignalState,
    adapt_breadth,
    adapt_mcclellan,
    adapt_mcclellan_summation,
    adapt_pe,
    adapt_regime,
    adapt_rs,
    adapt_sector_rs,
    combine_signals,
    get_adapter,
)
from backend.services.simulation.tax_engine import (
    FIFOLotTracker,
    IndianTaxRates,
    LotDisposal,
    TaxLot,
    compute_annual_tax_summary,
    compute_tax_on_disposal,
)

__all__ = [
    "SimulationService",
    # Signal adapters
    "SignalState",
    "SignalPoint",
    "SignalSeries",
    "adapt_breadth",
    "adapt_mcclellan",
    "adapt_rs",
    "adapt_pe",
    "adapt_regime",
    "adapt_sector_rs",
    "adapt_mcclellan_summation",
    "combine_signals",
    "get_adapter",
    # Tax engine
    "FIFOLotTracker",
    "IndianTaxRates",
    "LotDisposal",
    "TaxLot",
    "compute_annual_tax_summary",
    "compute_tax_on_disposal",
]
