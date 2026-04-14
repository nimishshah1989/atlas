"""Simulation Engine routes — V3 endpoints.

POST /run   — V3-4: execute a backtest simulation
GET  /      — V3-5: list saved simulations (stub, returns 501)
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.db.session import get_db
from backend.models.simulation import SimulationRunRequest, SimulationRunResponse
from backend.services.simulation.service import SimulationService

router = APIRouter(prefix="/api/v1/simulate", tags=["simulation"])


@router.post("/run", response_model=SimulationRunResponse)
async def run_simulation(
    request: SimulationRunRequest,
    session: AsyncSession = Depends(get_db),
) -> SimulationRunResponse:
    """Execute a backtest simulation.

    Accepts a SimulationConfig and returns the full simulation result including
    daily portfolio values, transactions, analytics summary, and tax breakdown.
    """
    jip = JIPDataService(session)
    service = SimulationService(session)

    try:
        result = await service.run_backtest(config=request.config, jip=jip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))

    freshness = await jip.get_data_freshness()

    # Compute staleness
    last_update = freshness.get("last_update") if freshness else None
    staleness = _compute_staleness(last_update)

    return SimulationRunResponse(
        result=result,
        data_as_of=result.data_as_of,
        staleness=staleness,
    )


@router.get("/", status_code=501)
async def list_simulations() -> dict[str, str]:
    """List saved simulations (stub — V3-5 implements)."""
    raise HTTPException(
        status_code=501,
        detail="Simulation listing not yet implemented (V3-5)",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_staleness(last_update: object) -> str:
    """Determine data staleness: FRESH | STALE | EXPIRED."""
    if last_update is None:
        return "STALE"

    try:
        if isinstance(last_update, str):
            update_dt = datetime.datetime.fromisoformat(last_update)
        elif isinstance(last_update, datetime.datetime):
            update_dt = last_update
        elif isinstance(last_update, datetime.date):
            update_dt = datetime.datetime.combine(
                last_update, datetime.time.min, tzinfo=datetime.timezone.utc
            )
        else:
            return "STALE"

        if update_dt.tzinfo is None:
            update_dt = update_dt.replace(tzinfo=datetime.timezone.utc)

        now = datetime.datetime.now(tz=datetime.timezone.utc)
        age_hours = (now - update_dt).total_seconds() / 3600

        if age_hours <= 24:
            return "FRESH"
        elif age_hours <= 72:
            return "STALE"
        else:
            return "EXPIRED"
    except (ValueError, TypeError, AttributeError):
        return "STALE"
