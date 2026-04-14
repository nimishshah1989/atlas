"""V3 Simulation Engine — foundation package."""

from backend.services.simulation.service import SimulationService
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
    "FIFOLotTracker",
    "IndianTaxRates",
    "LotDisposal",
    "TaxLot",
    "compute_annual_tax_summary",
    "compute_tax_on_disposal",
]
