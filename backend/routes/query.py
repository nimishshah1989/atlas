"""UQL query endpoints — POST /api/v1/query and POST /api/v1/query/template.

Both endpoints are thin shims over :mod:`backend.services.uql.engine`. The
route layer owns request parsing + JIP wiring; the engine owns safety,
optimization, execution, include resolution, and ``_meta``. Wired in
V2-UQL-AGG-14 per ``orchestrator/plan.yaml``.

§17.5–17.7 conformance is verified end-to-end by
``scripts/check-api-standard.py`` (criteria ``uql-01-aggregations``,
``uql-02-timeseries``, ``uql-03-templates``).
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.db.session import get_db
from backend.models.schemas import UQLRequest, UQLResponse
from backend.services.uql import engine

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["query"])


class TemplateRequest(BaseModel):
    """Body for ``POST /api/v1/query/template``.

    ``template`` is the registry key (see
    ``backend/services/uql/templates.py::REGISTRY``); ``params`` is the
    builder-specific param dict (may be omitted for parameterless
    templates).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"template": "top_rs_gainers", "params": {"limit": 5}},
                {"template": "sector_rotation", "params": {}},
                {"template": "breadth_dashboard", "params": {}},
            ]
        }
    )

    template: str = Field(min_length=1)
    params: Optional[dict[str, Any]] = None


@router.post(
    "/query",
    response_model=UQLResponse,
    summary="Execute a raw UQL query",
    description=(
        "Spec §17.5–17.7. Accepts a full UQL envelope — snapshot, "
        "aggregation (`group_by` + `aggregations`), or `mode='timeseries'` "
        "with `time_range`/`granularity`. Every fixed endpoint under "
        "`/stocks` and `/mf` is a thin wrapper over this route, so any "
        "payload the engine accepts here is safe to ship."
    ),
    responses={
        200: {"description": "Query executed — records + total + _meta"},
        400: {"description": "UQL validation rejection (safety, limits, shape)"},
        503: {"description": "Entity partition missing (FR-019)"},
    },
)
async def execute_query(
    request: UQLRequest,
    db: AsyncSession = Depends(get_db),
) -> UQLResponse:
    """Execute a raw UQL request via :func:`engine.execute`."""
    jip = JIPDataService(db)
    return await engine.execute(request, jip=jip)


@router.post(
    "/query/template",
    response_model=UQLResponse,
    summary="Execute a named UQL template",
    description=(
        "Spec §17.7. Dispatches a registered template "
        "(`backend/services/uql/templates.py::REGISTRY`) with optional "
        "params. Adding a template requires no route code."
    ),
    responses={
        200: {"description": "Template executed — same shape as /query"},
        404: {"description": "Template name not in registry"},
    },
)
async def execute_query_template(
    request: TemplateRequest,
    db: AsyncSession = Depends(get_db),
) -> UQLResponse:
    """Execute a named UQL template via :func:`engine.execute_template`."""
    jip = JIPDataService(db)
    return await engine.execute_template(request.template, request.params, jip=jip)
