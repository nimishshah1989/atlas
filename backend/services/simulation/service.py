"""SimulationService — stub for V3 simulation engine.

V3-2+ chunks implement the actual engine (tax, signals, backtest).
This stub provides the DI wiring and interface contract.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.simulation import SimulationConfig, SimulationResult

log = structlog.get_logger()


class SimulationService:
    """Simulation engine facade — wired as a FastAPI dependency."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def run_backtest(self, config: SimulationConfig) -> SimulationResult:
        """Execute a backtest simulation. Stub until V3-4."""
        log.info(
            "simulation_run_stub",
            signal=config.signal.value,
            instrument=config.instrument,
        )
        raise NotImplementedError("Simulation engine not yet implemented (V3-4)")
