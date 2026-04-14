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

    Args:
        db: Async DB session.
        agent_id: Identifier of the agent producing this finding.
        agent_type: Type/class of the agent.
        entity: Target entity (e.g. stock ticker).
        entity_type: Type of entity (e.g. "equity").
        finding_type: Category of finding (e.g. "technical", "sentiment").
        title: Short title for the finding.
        content: Full text of the finding.
        confidence: Decimal confidence score in [0, 1].
        data_as_of: Timezone-aware datetime this data applies to.
        evidence: Optional supporting evidence dict (no Decimal values — use str).
        tags: Optional list of tag strings.
        expires_hours: Hours until this finding expires (default 168 = 1 week).

    Returns:
        The stored AtlasIntelligence ORM row.

    Raises:
        ValueError: if confidence is not in [0, 1] or data_as_of is naive.
        EmbeddingError: never raised — embedding failures are logged and skipped
            (System Guarantee #3: fault-tolerant, partial data > no data).
    """
    if data_as_of.tzinfo is None:
        raise ValueError("data_as_of must be timezone-aware")
    if not (Decimal("0") <= confidence <= Decimal("1")):
        raise ValueError(f"confidence must be in [0, 1], got {confidence}")

    embed_text = f"{title} | {content} | Entity: {entity}"
    embedding_vector: list[float] | None = None
    try:
        embedding_vector = await embed(embed_text)
    except EmbeddingError:
        log.warning(
            "embedding_unavailable",
            agent_id=agent_id,
            entity=entity,
            detail="Finding will be stored without embedding vector",
        )

    expires_at = data_as_of + timedelta(hours=expires_hours)

    # Sanitize evidence: Decimal values break JSONB INSERT
    safe_evidence = _sanitize_for_jsonb(evidence or {})

    # ON CONFLICT using named partial unique index uq_intel_natural_key
    # Index: (agent_id, COALESCE(entity, ''), title, data_as_of) WHERE is_deleted = false
    # We reference it by constraint name in on_conflict_do_update.
    row_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    values: dict[str, Any] = {
        "id": row_id,
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

    # Use raw SQL for the upsert to handle the functional index constraint
    # and to avoid pgvector NULL type mismatch on the embedding column.
    # Two-phase: upsert the row without embedding, then update embedding separately.
    #
    # PostgreSQL ON CONFLICT with partial+functional indexes requires specifying
    # the exact index expression in the conflict_target, not the constraint name.
    # The index is: (agent_id, COALESCE(entity, ''), title, data_as_of) WHERE is_deleted = false
    # Use CAST() not ::type — asyncpg rejects ::type when :param names are present
    # (SQLAlchemy Param-Cast Collision bug pattern)
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

    import json as _json

    params = {
        **values,
        "evidence": _json.dumps(safe_evidence),
        "tags": list(tags or []),
    }
    # Convert Decimal to string for the query param (asyncpg doesn't accept Decimal directly)
    params["confidence"] = str(confidence)

    upsert_result = await db.execute(upsert_sql, params)
    returned_id = upsert_result.scalar_one()

    # Update embedding via raw SQL to avoid pgvector type mismatch (only if embedding available)
    # Use CAST() not ::vector — asyncpg rejects ::type with :param syntax
    if embedding_vector is not None:
        embed_sql = text(
            "UPDATE atlas_intelligence SET embedding = CAST(:vec AS vector) WHERE id = :rid"
        )
        await db.execute(embed_sql, {"vec": str(embedding_vector), "rid": str(returned_id)})

    await db.commit()

    # Fetch and return the full ORM object
    stmt = select(AtlasIntelligence).where(AtlasIntelligence.id == returned_id)
    fetch_result = await db.execute(stmt)
    row = fetch_result.scalar_one()

    log.info(
        "finding_stored",
        id=str(returned_id),
        agent_id=agent_id,
        entity=entity,
        finding_type=finding_type,
    )
    return row


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
    """Vector similarity search with metadata filters.

    Args:
        db: Async DB session.
        query: Natural language query string for semantic search.
        entity: Optional filter by entity name.
        entity_type: Optional filter by entity type.
        finding_type: Optional filter by finding type.
        agent_id: Optional filter by agent ID.
        min_confidence: Minimum confidence score (Decimal). Default 0.5.
        max_age_hours: Maximum age of findings in hours. Default 168.
        top_k: Number of results to return. Default 10.

    Returns:
        List of AtlasIntelligence rows ordered by cosine similarity (most similar first).
    """
    query_vector = await embed(query)
    vec_str = str(query_vector)

    now = datetime.now(timezone.utc)
    min_data_as_of = now - timedelta(hours=max_age_hours)

    # Build the vector search query using pgvector cosine distance (<=>)
    # Lower cosine distance = more similar. ORDER BY ASC for most-similar first.
    # Use raw SQL to avoid ORM limitations with pgvector operators.
    where_clauses = [
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
        "min_data_as_of": min_data_as_of,
    }

    if entity is not None:
        where_clauses.append("entity = :entity")
        params["entity"] = entity
    if entity_type is not None:
        where_clauses.append("entity_type = :entity_type")
        params["entity_type"] = entity_type
    if finding_type is not None:
        where_clauses.append("finding_type = :finding_type")
        params["finding_type"] = finding_type
    if agent_id is not None:
        where_clauses.append("agent_id = :agent_id")
        params["agent_id"] = agent_id

    where_str = " AND ".join(where_clauses)

    # Use CAST() not ::vector — asyncpg rejects ::type with :param syntax
    search_sql = text(
        f"""
        SELECT id
        FROM atlas_intelligence
        WHERE {where_str}
        ORDER BY embedding <=> CAST(:query_vec AS vector)
        LIMIT :top_k
        """
    )

    id_result = await db.execute(search_sql, params)
    ids = [row[0] for row in id_result.fetchall()]

    if not ids:
        return []

    # Fetch full ORM objects in similarity order
    stmt = select(AtlasIntelligence).where(AtlasIntelligence.id.in_(ids))
    fetch_result = await db.execute(stmt)
    rows_by_id = {row.id: row for row in fetch_result.scalars().all()}

    # Preserve similarity ordering from vector search
    ordered = [rows_by_id[row_id] for row_id in ids if row_id in rows_by_id]

    log.info(
        "intelligence_searched",
        query_len=len(query),
        results=len(ordered),
        entity=entity,
        finding_type=finding_type,
    )
    return ordered


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
