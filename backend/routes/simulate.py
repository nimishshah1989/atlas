"""Simulation Engine routes — V3 endpoints.

POST /run             — V3-4: execute a backtest simulation
GET  /                — V3-5: list saved simulations
GET  /{id}            — V3-5: get full simulation detail
POST /save            — V3-5: save config (without running)
DELETE /{id}          — V3-5: soft-delete a simulation
POST /auto-loop/run   — V3-5: trigger auto-loop re-run for all configured sims
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from backend.clients.jip_data_service import JIPDataService
from backend.db.session import get_db
from backend.models.simulation import (
    AutoLoopResponse,
    SimulationDetailResponse,
    SimulationListResponse,
    SimulationRunRequest,
    SimulationRunResponse,
    SimulationSaveRequest,
    SimulationSaveResponse,
)
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
        sim_result = await service.run_backtest(config=request.config, jip=jip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))

    freshness = await jip.get_data_freshness()

    # Compute staleness
    last_update = freshness.get("last_update") if freshness else None
    staleness = _compute_staleness(last_update)

    return SimulationRunResponse(
        result=sim_result,
        data_as_of=sim_result.data_as_of,
        staleness=staleness,
    )


# NOTE: /save and /auto-loop/run MUST be registered before /{id} to prevent
# FastAPI treating "save" or "auto-loop" as a UUID path parameter.


@router.post("/save", response_model=SimulationSaveResponse, status_code=201)
async def save_simulation_config(
    request: SimulationSaveRequest,
    session: AsyncSession = Depends(get_db),
) -> SimulationSaveResponse:
    """Save a simulation configuration without running the backtest.

    Used for setting up auto-loop configurations that will be re-run on a schedule.
    """
    service = SimulationService(session)

    try:
        sim = await service.save_config(
            config=request.config,
            name=request.name,
            is_auto_loop=request.is_auto_loop,
            auto_loop_cron=request.auto_loop_cron,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return SimulationSaveResponse(
        id=sim.id,
        name=sim.name,
        created_at=sim.created_at,
    )


@router.post("/auto-loop/run", response_model=AutoLoopResponse)
async def trigger_auto_loop(
    session: AsyncSession = Depends(get_db),
) -> AutoLoopResponse:
    """Trigger auto-loop re-run for all saved simulations with is_auto_loop=True.

    Runs each simulation independently — one failure does not abort others.
    Returns per-simulation status and KPI deltas vs previous run.
    """
    jip = JIPDataService(session)
    service = SimulationService(session)

    results = await service.run_auto_loop(jip=jip)

    ran_at = datetime.datetime.now(tz=datetime.timezone.utc)
    succeeded = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "error")

    return AutoLoopResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        ran_at=ran_at,
    )


@router.get("/", response_model=SimulationListResponse)
async def list_simulations(
    user_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    session: AsyncSession = Depends(get_db),
) -> SimulationListResponse:
    """List saved simulations, newest first, excluding soft-deleted."""
    from backend.models.simulation import SimulationConfig, SimulationListItem

    service = SimulationService(session)
    sims = await service.list_simulations(user_id=user_id, limit=limit)

    items = []
    for sim in sims:
        try:
            config = SimulationConfig.model_validate(sim.config or {})
        except (ValueError, TypeError):
            continue  # skip malformed rows — fault tolerance

        items.append(
            SimulationListItem(
                id=sim.id,
                name=sim.name,
                config=config,
                created_at=sim.created_at,
                is_auto_loop=bool(sim.is_auto_loop),
            )
        )

    return SimulationListResponse(
        simulations=items,
        count=len(items),
        data_as_of=datetime.datetime.now(tz=datetime.timezone.utc),
    )


@router.get("/{sim_id}", response_model=SimulationDetailResponse)
async def get_simulation(
    sim_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> SimulationDetailResponse:
    """Fetch full detail for a single simulation by ID."""
    from backend.models.simulation import (
        DailyValue,
        SimulationConfig,
        SimulationResult,
        SimulationSummary,
        TaxSummary,
        TransactionRecord,
    )

    service = SimulationService(session)
    sim = await service.get_simulation(str(sim_id))

    if sim is None:
        raise HTTPException(status_code=404, detail=f"Simulation {sim_id} not found")

    # Reconstruct result from JSONB — all financial fields come back as str from JSONB
    try:
        config = SimulationConfig.model_validate(sim.config or {})
        summary = SimulationSummary.model_validate(sim.result_summary or {})
        tax_summary = TaxSummary.model_validate(sim.tax_summary or {})
        daily_values = [DailyValue.model_validate(dv) for dv in (sim.daily_values or [])]
        transactions = [TransactionRecord.model_validate(tx) for tx in (sim.transactions or [])]
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Simulation data is malformed: {exc}",
        )

    sim_result = SimulationResult(
        summary=summary,
        daily_values=daily_values,
        transactions=transactions,
        tax_summary=tax_summary,
        tear_sheet_url=None,
        data_as_of=sim.created_at,
    )

    return SimulationDetailResponse(
        id=sim.id,
        name=sim.name,
        config=config,
        result=sim_result,
        created_at=sim.created_at,
        is_auto_loop=bool(sim.is_auto_loop),
        auto_loop_cron=sim.auto_loop_cron,
        last_auto_run=sim.last_auto_run,
        data_as_of=sim.created_at,
    )


@router.delete("/{sim_id}", status_code=204)
async def delete_simulation(
    sim_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a simulation by ID. Returns 404 if not found."""
    service = SimulationService(session)
    deleted = await service.delete_simulation(str(sim_id))

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Simulation {sim_id} not found")


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
