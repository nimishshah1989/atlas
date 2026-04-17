"""Alerts API routes — V6-7.

GET  /api/alerts              — list alerts with optional source + unread filters
POST /api/alerts/{alert_id}/read — mark a single alert as read
GET  /api/alerts/rules        — stub (501)
POST /api/alerts/rules        — stub (501)

IMPORTANT: static /rules routes are registered BEFORE /{alert_id}/read to
avoid the FastAPI path-param collision (literal "rules" captured as int param).
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasAlert
from backend.db.session import get_db
from backend.models.alert import AlertReadResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ---------------------------------------------------------------------------
# STATIC /rules routes — MUST be before /{alert_id}/read
# ---------------------------------------------------------------------------


@router.get("/rules")
async def list_alert_rules() -> None:
    """Alert rules CRUD — not yet implemented."""
    raise HTTPException(status_code=501, detail="Alert rules not yet implemented")


@router.post("/rules")
async def create_alert_rule() -> None:
    """Alert rules CRUD — not yet implemented."""
    raise HTTPException(status_code=501, detail="Alert rules not yet implemented")


# ---------------------------------------------------------------------------
# GET / — list alerts
# ---------------------------------------------------------------------------


@router.get("")
async def list_alerts(
    source: Optional[str] = None,
    unread: Optional[bool] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return alerts with optional source + unread filters.

    Response shape: §20.4 envelope with data + _meta.
    """
    stmt = select(AtlasAlert).where(AtlasAlert.is_deleted == False)  # noqa: E712

    if source is not None:
        stmt = stmt.where(AtlasAlert.source == source)

    if unread is True:
        stmt = stmt.where(AtlasAlert.is_read == False)  # noqa: E712
    elif unread is False:
        stmt = stmt.where(AtlasAlert.is_read == True)  # noqa: E712

    # Order by most-recent first
    stmt = stmt.order_by(AtlasAlert.created_at.desc())

    _limit = limit if limit is not None else 50
    _offset = offset if offset is not None else 0

    stmt = stmt.offset(_offset).limit(_limit)

    db_result = await session.execute(stmt)
    rows = db_result.scalars().all()

    items = []
    for row in rows:
        instrument_str = str(row.instrument_id) if row.instrument_id is not None else None
        items.append(
            {
                "id": row.id,
                "source": row.source,
                "symbol": row.symbol,
                "instrument_id": instrument_str,
                "alert_type": row.alert_type,
                "message": row.message,
                "metadata": row.metadata_json,
                "rs_at_alert": row.rs_at_alert,
                "quadrant_at_alert": row.quadrant_at_alert,
                "is_read": row.is_read,
                "created_at": row.created_at,
            }
        )

    log.info(
        "alerts_listed",
        source=source,
        unread=unread,
        returned=len(items),
        offset=_offset,
        limit=_limit,
    )

    return {
        "data": items,
        "_meta": {
            "returned": len(items),
            "offset": _offset,
            "limit": _limit,
            "has_more": len(items) == _limit,
        },
    }


# ---------------------------------------------------------------------------
# POST /{alert_id}/read — mark alert as read
# ---------------------------------------------------------------------------


@router.post("/{alert_id}/read", response_model=AlertReadResponse)
async def mark_alert_read(
    alert_id: int,
    session: AsyncSession = Depends(get_db),
) -> AlertReadResponse:
    """Mark a single alert as read. Returns 404 if not found."""
    stmt = select(AtlasAlert).where(
        AtlasAlert.id == alert_id,
        AtlasAlert.is_deleted == False,  # noqa: E712
    )
    db_result = await session.execute(stmt)
    alert = db_result.scalar_one_or_none()

    if alert is None:
        log.warning("alert_not_found", alert_id=alert_id)
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert.is_read = True
    await session.commit()

    log.info("alert_marked_read", alert_id=alert_id)
    return AlertReadResponse(id=alert.id, is_read=True, message="Alert marked as read")
