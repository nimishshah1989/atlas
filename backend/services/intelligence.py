"""Intelligence writer service — store and retrieve ATLAS intelligence findings.

Spec §6: AtlasIntelligence table. Idempotent upserts, vector similarity search.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasIntelligence
from backend.services.embedding import EmbeddingError, embed

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def store_finding(
    db: AsyncSession,
    agent_id: str,
    agent_type: str,
    entity: str,
    entity_type: str,
    finding_type: str,
    title: str,
    content: str,
    confidence: Decimal,
    data_as_of: datetime,
    evidence: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    expires_hours: int = 168,
) -> AtlasIntelligence:
    """Store a finding. Idempotent: same (agent_id, entity, title, data_as_of) upserts.

    Raises:
        ValueError: if confidence is not in [0, 1] or data_as_of is naive.
    """
    if data_as_of.tzinfo is None:
        raise ValueError("data_as_of must be timezone-aware")
    if not (Decimal("0") <= confidence <= Decimal("1")):
        raise ValueError(f"confidence must be in [0, 1], got {confidence}")

    embedding_vector = await _try_embed(agent_id, entity, title, content)
    expires_at = data_as_of + timedelta(hours=expires_hours)
    safe_evidence = _sanitize_for_jsonb(evidence or {})

    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "agent_id": agent_id,
        "agent_type": agent_type,
        "entity": entity,
        "entity_type": entity_type,
        "finding_type": finding_type,
        "title": title,
        "content": content,
        "confidence": confidence,
        "evidence": safe_evidence,
        "tags": tags or [],
        "data_as_of": data_as_of,
        "expires_at": expires_at,
        "is_validated": False,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }

    returned_id = await _upsert_finding(db, values, safe_evidence, confidence, tags)

    if embedding_vector is not None:
        await _update_embedding(db, returned_id, embedding_vector)

    await db.commit()

    stmt = select(AtlasIntelligence).where(AtlasIntelligence.id == returned_id)
    row = (await db.execute(stmt)).scalar_one()

    log.info(
        "finding_stored",
        id=str(returned_id),
        agent_id=agent_id,
        entity=entity,
        finding_type=finding_type,
    )
    return row


async def _try_embed(
    agent_id: str,
    entity: str,
    title: str,
    content: str,
) -> list[float] | None:
    """Attempt embedding, returning None on failure (fault-tolerant)."""
    try:
        return await embed(f"{title} | {content} | Entity: {entity}")
    except EmbeddingError:
        log.warning(
            "embedding_unavailable",
            agent_id=agent_id,
            entity=entity,
            detail="Finding will be stored without embedding vector",
        )
        return None


async def _upsert_finding(
    db: AsyncSession,
    values: dict[str, Any],
    safe_evidence: dict[str, Any],
    confidence: Decimal,
    tags: list[str] | None,
) -> uuid.UUID:
    """Execute the ON CONFLICT upsert, return the row ID."""
    import json as _json

    upsert_sql = text(
        """
        INSERT INTO atlas_intelligence (
            id, agent_id, agent_type, entity, entity_type, finding_type,
            title, content, confidence, evidence, tags,
            data_as_of, expires_at, is_validated, is_deleted, created_at, updated_at
        ) VALUES (
            :id, :agent_id, :agent_type, :entity, :entity_type, :finding_type,
            :title, :content, CAST(:confidence AS numeric), CAST(:evidence AS jsonb), :tags,
            :data_as_of, :expires_at, :is_validated, :is_deleted, :created_at, :updated_at
        )
        ON CONFLICT (agent_id, COALESCE(entity, ''), title, data_as_of) WHERE is_deleted = false
        DO UPDATE SET
            content       = EXCLUDED.content,
            confidence    = CAST(EXCLUDED.confidence AS numeric),
            evidence      = EXCLUDED.evidence,
            tags          = EXCLUDED.tags,
            expires_at    = EXCLUDED.expires_at,
            agent_type    = EXCLUDED.agent_type,
            entity_type   = EXCLUDED.entity_type,
            finding_type  = EXCLUDED.finding_type,
            updated_at    = EXCLUDED.updated_at
        RETURNING id
        """
    )

    params = {
        **values,
        "evidence": _json.dumps(safe_evidence),
        "tags": list(tags or []),
        "confidence": str(confidence),
    }
    result = await db.execute(upsert_sql, params)
    returned_id: uuid.UUID = result.scalar_one()
    return returned_id


async def _update_embedding(
    db: AsyncSession,
    row_id: uuid.UUID,
    vector: list[float],
) -> None:
    """Update embedding via raw SQL (two-phase write for pgvector)."""
    sql = text("UPDATE atlas_intelligence SET embedding = CAST(:vec AS vector) WHERE id = :rid")
    await db.execute(sql, {"vec": str(vector), "rid": str(row_id)})


async def get_relevant_intelligence(
    db: AsyncSession,
    query: str,
    entity: str | None = None,
    entity_type: str | None = None,
    finding_type: str | None = None,
    agent_id: str | None = None,
    min_confidence: Decimal = Decimal("0.5"),
    max_age_hours: int = 168,
    top_k: int = 10,
) -> list[AtlasIntelligence]:
    """Vector similarity search with metadata filters."""
    query_vector = await embed(query)
    now = datetime.now(timezone.utc)

    where_str, params = _build_search_filters(
        str(query_vector),
        now,
        min_confidence,
        max_age_hours,
        top_k,
        entity,
        entity_type,
        finding_type,
        agent_id,
    )

    search_sql = text(f"""
        SELECT id FROM atlas_intelligence
        WHERE {where_str}
        ORDER BY embedding <=> CAST(:query_vec AS vector)
        LIMIT :top_k
    """)

    ids = [row[0] for row in (await db.execute(search_sql, params)).fetchall()]
    if not ids:
        return []

    stmt = select(AtlasIntelligence).where(AtlasIntelligence.id.in_(ids))
    rows_by_id = {r.id: r for r in (await db.execute(stmt)).scalars().all()}
    ordered = [rows_by_id[rid] for rid in ids if rid in rows_by_id]

    log.info(
        "intelligence_searched",
        query_len=len(query),
        results=len(ordered),
        entity=entity,
        finding_type=finding_type,
    )
    return ordered


def _build_search_filters(
    vec_str: str,
    now: datetime,
    min_confidence: Decimal,
    max_age_hours: int,
    top_k: int,
    entity: str | None,
    entity_type: str | None,
    finding_type: str | None,
    agent_id: str | None,
) -> tuple[str, dict[str, Any]]:
    """Build WHERE clause and params for vector search."""
    clauses = [
        "is_deleted = false",
        "(expires_at IS NULL OR expires_at > :now)",
        "(confidence IS NULL OR confidence >= :min_confidence)",
        "data_as_of >= :min_data_as_of",
        "embedding IS NOT NULL",
    ]
    params: dict[str, Any] = {
        "query_vec": vec_str,
        "top_k": top_k,
        "now": now,
        "min_confidence": str(min_confidence),
        "min_data_as_of": now - timedelta(hours=max_age_hours),
    }
    for name, val in [
        ("entity", entity),
        ("entity_type", entity_type),
        ("finding_type", finding_type),
        ("agent_id", agent_id),
    ]:
        if val is not None:
            clauses.append(f"{name} = :{name}")
            params[name] = val
    return " AND ".join(clauses), params


async def get_finding_by_id(
    db: AsyncSession,
    finding_id: uuid.UUID,
) -> AtlasIntelligence | None:
    """Fetch a single finding by primary key. Returns None if not found or deleted."""
    stmt = select(AtlasIntelligence).where(
        AtlasIntelligence.id == finding_id,
        AtlasIntelligence.is_deleted == False,  # noqa: E712
    )
    query_result = await db.execute(stmt)
    return query_result.scalar_one_or_none()


async def list_findings(
    db: AsyncSession,
    entity: str | None = None,
    entity_type: str | None = None,
    finding_type: str | None = None,
    agent_id: str | None = None,
    min_confidence: Decimal | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AtlasIntelligence]:
    """List findings with optional filters. Ordered by created_at desc."""
    stmt = select(AtlasIntelligence).where(
        AtlasIntelligence.is_deleted == False  # noqa: E712
    )

    if entity is not None:
        stmt = stmt.where(AtlasIntelligence.entity == entity)
    if entity_type is not None:
        stmt = stmt.where(AtlasIntelligence.entity_type == entity_type)
    if finding_type is not None:
        stmt = stmt.where(AtlasIntelligence.finding_type == finding_type)
    if agent_id is not None:
        stmt = stmt.where(AtlasIntelligence.agent_id == agent_id)
    if min_confidence is not None:
        stmt = stmt.where(AtlasIntelligence.confidence >= min_confidence)

    stmt = stmt.order_by(AtlasIntelligence.created_at.desc()).offset(offset).limit(limit)
    findings_result = await db.execute(stmt)
    return list(findings_result.scalars().all())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_for_jsonb(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert Decimal values to strings for JSONB compatibility.

    Decimal values in dicts break JSONB INSERT (asyncpg serialization error).
    """
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, Decimal):
            sanitized[key] = str(value)
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_for_jsonb(value)
        elif isinstance(value, list):
            sanitized[key] = [str(v) if isinstance(v, Decimal) else v for v in value]
        else:
            sanitized[key] = value
    return sanitized
