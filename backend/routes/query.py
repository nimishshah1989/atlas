"""UQL Query endpoint — Bloomberg-grade unified query layer (V1: equity only)."""

import time
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.db.session import get_db
from backend.models.schemas import ResponseMeta, UQLRequest, UQLResponse

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["query"])


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert Decimal/UUID/date values to JSON-safe types."""
    serialized: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            serialized[key] = str(value)
        elif hasattr(value, "isoformat"):
            serialized[key] = value.isoformat()
        elif hasattr(value, "hex"):
            serialized[key] = str(value)
        else:
            serialized[key] = value
    return serialized


@router.post("/query", response_model=UQLResponse)
async def execute_query(
    request: UQLRequest,
    db: AsyncSession = Depends(get_db),
) -> UQLResponse:
    """Execute a UQL query. V1 supports entity_type='equity' only."""
    t0 = time.monotonic()

    if request.entity_type != "equity":
        raise HTTPException(
            status_code=400,
            detail=f"V1 only supports entity_type='equity', got '{request.entity_type}'",
        )

    svc = JIPDataService(db)

    filters = [{"field": f.field, "op": f.op.value, "value": f.value} for f in request.filters]
    sort = [{"field": s.field, "direction": s.direction.value} for s in request.sort]

    rows, total = await svc.query_equity(
        filters=filters,
        sort=sort,
        limit=request.limit,
        offset=request.offset,
        fields=request.fields,
    )

    elapsed = int((time.monotonic() - t0) * 1000)

    return UQLResponse(
        records=[_serialize_row(row) for row in rows],
        total=total,
        meta=ResponseMeta(record_count=len(rows), query_ms=elapsed),
    )
