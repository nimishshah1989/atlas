"""Pydantic v2 response models for the routine visibility endpoint.

V11-0: GET /api/v1/system/routines — one entry per JIP data routine
declared in docs/specs/jip-source-manifest.yaml.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RoutineLastRun(BaseModel):
    run_id: Optional[str] = None
    status: Optional[str] = None  # success | partial | failed
    rows_fetched: Optional[int] = None
    rows_inserted: Optional[int] = None
    rows_updated: Optional[int] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    ran_at: Optional[datetime] = None


class RoutineEntry(BaseModel):
    id: str
    tables: list[str]
    cadence: str
    schedule: Optional[str] = None
    source: Optional[str] = None
    manifest_status: str  # live | partial | missing | planned
    is_new: bool  # True = from new_routines (not yet built)
    priority: Optional[str] = None  # P1/P2/P3 for new routines
    sla_freshness_hours: Optional[int] = None
    last_run: Optional[RoutineLastRun] = None
    sla_breached: bool
    display_status: str  # live | partial | sla_breached | missing | planned | unknown


class RoutinesResponse(BaseModel):
    routines: list[RoutineEntry]
    total: int
    live_count: int
    sla_breached_count: int
    data_available: bool  # False if de_routine_runs missing/empty
    as_of: datetime
