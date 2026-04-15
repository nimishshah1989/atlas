"""Intelligence API routes — store and search ATLAS intelligence findings."""

import time
from decimal import Decimal
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.models.intelligence import (
    FindingCreate,
    FindingSummary,
    FindingSummaryEnvelope,
    IntelligenceListResponse,
    IntelligenceSearchResponse,
)
from backend.models.schemas import ResponseMeta
from backend.services.intelligence import (
    get_finding_by_id,
    get_relevant_intelligence,
    list_findings,
    store_finding,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


def _to_summary(row: object) -> FindingSummary:
    """Convert an AtlasIntelligence ORM row to FindingSummary schema."""
    from backend.db.models import AtlasIntelligence

    r: AtlasIntelligence = row  # type: ignore[assignment]
    return FindingSummary(
        id=r.id,
        agent_id=r.agent_id,
        agent_type=r.agent_type,
        entity=r.entity,
        entity_type=r.entity_type,
        finding_type=r.finding_type,
        title=r.title,
        content=r.content,
        confidence=r.confidence,
        evidence=r.evidence,
        tags=r.tags,
        data_as_of=r.data_as_of,
        expires_at=r.expires_at,
        is_validated=r.is_validated,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.post("/findings", response_model=FindingSummary, status_code=201)
async def create_finding(
    body: FindingCreate,
    db: AsyncSession = Depends(get_db),
) -> FindingSummary:
    """Store a new intelligence finding. Idempotent — same natural key upserts."""
    t0 = time.monotonic()

    try:
        row = await store_finding(
            db=db,
            agent_id=body.agent_id,
            agent_type=body.agent_type,
            entity=body.entity,
            entity_type=body.entity_type,
            finding_type=body.finding_type,
            title=body.title,
            content=body.content,
            confidence=body.confidence,
            data_as_of=body.data_as_of,
            evidence=body.evidence,
            tags=body.tags,
            expires_hours=body.expires_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    elapsed = int((time.monotonic() - t0) * 1000)
    log.info("finding_created", finding_id=str(row.id), entity=row.entity, query_ms=elapsed)
    return _to_summary(row)


@router.get("/search", response_model=IntelligenceSearchResponse)
async def search_intelligence(
    q: str = Query(..., description="Natural language search query"),
    entity: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    finding_type: Optional[str] = Query(None),
    min_confidence: Optional[Decimal] = Query(Decimal("0.5")),
    max_age_hours: Optional[int] = Query(168),
    top_k: Optional[int] = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> IntelligenceSearchResponse:
    """Vector similarity search over intelligence findings."""
    t0 = time.monotonic()

    rows = await get_relevant_intelligence(
        db=db,
        query=q,
        entity=entity,
        entity_type=entity_type,
        finding_type=finding_type,
        min_confidence=min_confidence or Decimal("0.5"),
        max_age_hours=max_age_hours or 168,
        top_k=top_k or 10,
    )

    findings = [_to_summary(r) for r in rows]
    elapsed = int((time.monotonic() - t0) * 1000)

    return IntelligenceSearchResponse(
        findings=findings,
        meta=ResponseMeta(record_count=len(findings), query_ms=elapsed),
    )


@router.get("/findings", response_model=IntelligenceListResponse)
async def list_intelligence_findings(
    entity: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    finding_type: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    min_confidence: Optional[Decimal] = Query(None),
    limit: Optional[int] = Query(50, ge=1, le=200),
    offset: Optional[int] = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> IntelligenceListResponse:
    """List intelligence findings with optional filters."""
    t0 = time.monotonic()

    rows = await list_findings(
        db=db,
        entity=entity,
        entity_type=entity_type,
        finding_type=finding_type,
        agent_id=agent_id,
        min_confidence=min_confidence,
        limit=limit or 50,
        offset=offset or 0,
    )

    findings = [_to_summary(r) for r in rows]
    elapsed = int((time.monotonic() - t0) * 1000)

    return IntelligenceListResponse(
        findings=findings,
        meta=ResponseMeta(record_count=len(findings), query_ms=elapsed),
    )


@router.get("/findings/{finding_id}", response_model=FindingSummaryEnvelope)
async def get_finding(
    finding_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FindingSummaryEnvelope:
    """Get a single intelligence finding by ID.

    Returns §20.4 standard envelope: ``{data: {...}, _meta: {...}}``.
    404 if the finding does not exist or is soft-deleted.
    """
    t0 = time.monotonic()

    row = await get_finding_by_id(db=db, finding_id=finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    elapsed = int((time.monotonic() - t0) * 1000)
    log.info("finding_fetched", finding_id=str(finding_id), query_ms=elapsed)
    return FindingSummaryEnvelope(
        finding=_to_summary(row),
        meta=ResponseMeta(record_count=1, query_ms=elapsed),
    )
