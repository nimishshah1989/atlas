"""Decision API routes — lifecycle management for ATLAS decisions."""

import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasDecision, DecisionActionEnum
from backend.db.session import get_db
from backend.models.schemas import (
    DecisionAction,
    DecisionActionRequest,
    DecisionListResponse,
    DecisionSignal,
    DecisionSummary,
    Quadrant,
    ResponseMeta,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


@router.get("", response_model=DecisionListResponse)
async def list_decisions(
    symbol: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: Optional[int] = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> DecisionListResponse:
    """List decisions, optionally filtered by symbol or action status."""
    t0 = time.monotonic()

    stmt = select(AtlasDecision).where(AtlasDecision.is_deleted == False)  # noqa: E712

    if symbol:
        stmt = stmt.where(AtlasDecision.symbol == symbol.upper())
    if action:
        stmt = stmt.where(AtlasDecision.action == DecisionActionEnum(action))

    stmt = stmt.order_by(AtlasDecision.created_at.desc()).limit(limit)

    query_result = await db.execute(stmt)
    rows = query_result.scalars().all()

    decisions = [
        DecisionSummary(
            id=r.id,
            symbol=r.symbol,
            signal=DecisionSignal(
                r.signal.value if hasattr(r.signal, "value") else r.signal
            ),
            quadrant=Quadrant(r.quadrant) if r.quadrant else None,
            reason=r.reason,
            created_at=r.created_at,
            action=DecisionAction(
                r.action.value if hasattr(r.action, "value") else r.action
            ),
            action_at=r.action_at,
            action_note=r.action_note,
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
) -> dict:
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
            action=DecisionActionEnum(request.action.value),
            action_at=now,
            action_note=request.note,
            updated_at=now,
        )
    )
    await db.commit()

    log.info("decision_actioned", id=str(decision_id), action=request.action.value)
    return {"status": "ok", "action": request.action.value}
