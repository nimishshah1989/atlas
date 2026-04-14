"""Simulation Engine routes — V3 stub endpoints.

All endpoints return 501 until V3-4 wires the engine.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/simulate", tags=["simulation"])


@router.post("/run", status_code=501)
async def run_simulation() -> dict[str, str]:
    """Execute a backtest simulation (stub — V3-4 implements)."""
    raise HTTPException(
        status_code=501,
        detail="Simulation engine not yet implemented (V3-4)",
    )


@router.get("/", status_code=501)
async def list_simulations() -> dict[str, str]:
    """List saved simulations (stub — V3-5 implements)."""
    raise HTTPException(
        status_code=501,
        detail="Simulation listing not yet implemented (V3-5)",
    )
