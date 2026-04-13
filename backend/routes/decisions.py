"""Decision API routes — lifecycle management for ATLAS decisions."""

import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasDecision
from backend.db.session import get_db
from backend.models.schemas import (
    DecisionAction,
    DecisionActionRequest,
    DecisionListResponse,
    DecisionSignal,
    DecisionSummary,
    ResponseMeta,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


@router.get("", response_model=DecisionListResponse)
async def list_decisions(
    entity: Optional[str] = Query(None),
    user_action: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> DecisionListResponse:
    """List decisions, optionally filtered by entity, user_action, or status."""
    t0 = time.monotonic()

    stmt = select(AtlasDecision).where(AtlasDecision.is_deleted == False)  # noqa: E712

    if entity:
        stmt = stmt.where(AtlasDecision.entity == entity.upper())
    if user_action:
        stmt = stmt.where(AtlasDecision.user_action == user_action)
    if status:
        stmt = stmt.where(AtlasDecision.status == status)

    stmt = stmt.order_by(AtlasDecision.created_at.desc()).limit(limit)

    query_result = await db.execute(stmt)
    rows = query_result.scalars().all()

    decisions = [
        DecisionSummary(
            id=r.id,
            entity=r.entity,
            entity_type=r.entity_type,
            decision_type=DecisionSignal(r.decision_type),
            rationale=r.rationale,
            confidence=r.confidence,
            horizon=r.horizon,
            horizon_end_date=r.horizon_end_date,
            status=r.status,
            source_agent=r.source_agent,
            created_at=r.created_at,
            user_action=DecisionAction(r.user_action) if r.user_action else None,
            user_action_at=r.user_action_at,
            user_notes=r.user_notes,
        )
        for r in rows
    ]

    elapsed = int((time.monotonic() - t0) * 1000)
    return DecisionListResponse(
        decisions=decisions,
        meta=ResponseMeta(record_count=len(decisions), query_ms=elapsed),
    )


@router.put("/{decision_id}/action")
async def update_decision_action(
    decision_id: UUID,
    request: DecisionActionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Accept, ignore, or override a decision."""
    stmt = select(AtlasDecision).where(
        AtlasDecision.id == decision_id,
        AtlasDecision.is_deleted == False,  # noqa: E712
    )
    lookup_result = await db.execute(stmt)
    decision = lookup_result.scalar_one_or_none()

    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")

    now = datetime.now(timezone.utc)
    await db.execute(
        update(AtlasDecision)
        .where(AtlasDecision.id == decision_id)
        .values(
            user_action=request.action.value,
            user_action_at=now,
            user_notes=request.note,
            updated_at=now,
        )
    )
    await db.commit()

    log.info("decision_actioned", id=str(decision_id), action=request.action.value)
    return {"status": "ok", "action": request.action.value}
