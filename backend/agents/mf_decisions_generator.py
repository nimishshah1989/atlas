"""MF Decisions Generator Agent — reads MF findings from atlas_intelligence and writes decisions.

Spec §23.2 extension: Downstream consumer of mf-rs-analyzer and mf-flow-analyzer findings.
Maps finding_type + quadrant/flow data to buy_signal / sell_signal / overweight / avoid
decisions in atlas_decisions.

This agent does NOT call any LLM. It is pure computation.
Idempotent: re-run with same data_as_of produces zero new decisions (check-before-insert).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasDecision, AtlasIntelligence
from backend.services.intelligence import list_findings

log = structlog.get_logger(__name__)

AGENT_ID = "mf-decisions-generator"
AGENT_TYPE = "computation"

# Horizon days for all MF decisions
HORIZON_DAYS = 20
HORIZON_LABEL = "20_days"

# Confidence scores per mapping
_CONF_STRONG = Decimal("0.85")
_CONF_MEDIUM = Decimal("0.80")
_CONF_WEAK = Decimal("0.75")
_CONF_WEAKER = Decimal("0.70")

# Source agents we consume findings from
_MF_RS_AGENT = "mf-rs-analyzer"
_MF_FLOW_AGENT = "mf-flow-analyzer"

# Finding types we consume
_MF_TRANSITION_TYPE = "mf_quadrant_transition"
_MF_FLOW_TYPE = "mf_flow_reversal"


# ---------------------------------------------------------------------------
# Mapping helpers — each returns (decision_type, confidence, invalidation_conditions)
# or None if the finding should be skipped (unknown quadrant/direction).
# ---------------------------------------------------------------------------


def _map_mf_quadrant_transition(
    finding: AtlasIntelligence,
) -> tuple[str, Decimal, list[str]] | None:
    """Map a mf_quadrant_transition finding to a decision.

    Confidence per spec:
      LEADING   → buy_signal  0.85
      IMPROVING → buy_signal  0.70
      WEAKENING → sell_signal 0.75
      LAGGING   → sell_signal 0.80
    """
    evidence = finding.evidence or {}
    quadrant = evidence.get("quadrant", "")

    if quadrant == "LEADING":
        return ("buy_signal", _CONF_STRONG, ["quadrant leaves LEADING"])
    elif quadrant == "IMPROVING":
        return ("buy_signal", _CONF_WEAKER, ["quadrant leaves IMPROVING"])
    elif quadrant == "WEAKENING":
        return ("sell_signal", _CONF_WEAK, ["quadrant leaves WEAKENING"])
    elif quadrant == "LAGGING":
        return ("sell_signal", _CONF_MEDIUM, ["quadrant leaves LAGGING"])
    return None


def _map_mf_flow_reversal(
    finding: AtlasIntelligence,
) -> tuple[str, Decimal, list[str]] | None:
    """Map a mf_flow_reversal finding to a decision.

    Confidence per spec:
      positive_to_negative → avoid      0.75
      negative_to_positive → overweight 0.70
    """
    evidence = finding.evidence or {}
    flow_direction = evidence.get("flow_direction", "")

    if flow_direction == "positive_to_negative":
        return ("avoid", _CONF_WEAK, ["flow reverses back"])
    elif flow_direction == "negative_to_positive":
        return ("overweight", _CONF_WEAKER, ["flow reverses"])
    return None


# ---------------------------------------------------------------------------
# Finding-type dispatch map
# ---------------------------------------------------------------------------

_FINDING_MAPPERS = {
    (_MF_RS_AGENT, _MF_TRANSITION_TYPE): _map_mf_quadrant_transition,
    (_MF_FLOW_AGENT, _MF_FLOW_TYPE): _map_mf_flow_reversal,
}


# ---------------------------------------------------------------------------
# Idempotency check
# ---------------------------------------------------------------------------


async def _decision_exists(
    db: AsyncSession,
    entity: str,
    decision_type: str,
    data_as_of_date: Any,
) -> bool:
    """Return True if a decision already exists for (entity, decision_type, source_agent,
    data_as_of)."""
    stmt = select(AtlasDecision.id).where(
        AtlasDecision.entity == entity,
        AtlasDecision.decision_type == decision_type,
        AtlasDecision.source_agent == AGENT_ID,
        AtlasDecision.data_as_of == data_as_of_date,
        AtlasDecision.is_deleted == False,  # noqa: E712
    )
    existing = await db.execute(stmt)
    return existing.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Sanitize supporting_data for JSONB (Decimal → str)
# ---------------------------------------------------------------------------


def _sanitize_for_jsonb(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert Decimal values to strings for JSONB compatibility."""
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


# ---------------------------------------------------------------------------
# Single finding → decision writer
# ---------------------------------------------------------------------------


async def _write_decision(
    db: AsyncSession,
    finding: AtlasIntelligence,
    decision_type: str,
    confidence: Decimal,
    invalidation_conditions: list[str],
    data_as_of_date: Any,
) -> bool:
    """Write one decision row. Returns True if written, False if skipped (idempotent)."""
    entity = finding.entity or ""
    if not entity:
        log.warning("skipping_finding_no_entity", finding_id=str(finding.id))
        return False

    # Idempotency: skip if same decision already exists for this data_as_of
    if await _decision_exists(db, entity, decision_type, data_as_of_date):
        log.debug(
            "decision_exists_skip",
            entity=entity,
            decision_type=decision_type,
            data_as_of=str(data_as_of_date),
        )
        return False

    horizon_end = data_as_of_date + timedelta(days=HORIZON_DAYS)

    supporting_data = _sanitize_for_jsonb(
        {
            "finding_id": str(finding.id),
            "finding_type": finding.finding_type,
            "agent_id": finding.agent_id,
            "evidence": finding.evidence or {},
        }
    )

    decision = AtlasDecision(
        id=uuid.uuid4(),
        entity=entity,
        entity_type=finding.entity_type or "mutual_fund",
        decision_type=decision_type,
        rationale=(f"Generated from {finding.finding_type} finding: {finding.title}"),
        supporting_data=supporting_data,
        confidence=confidence,
        source_agent=AGENT_ID,
        horizon=HORIZON_LABEL,
        horizon_end_date=horizon_end,
        invalidation_conditions=invalidation_conditions,
        status="active",
        data_as_of=data_as_of_date,
    )
    db.add(decision)
    await db.flush()  # Flush within the session; caller commits once per batch

    log.info(
        "mf_decision_written",
        entity=entity,
        decision_type=decision_type,
        finding_id=str(finding.id),
    )
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def _fetch_all_findings(
    db: AsyncSession,
    lookback_limit: int,
) -> list[tuple[AtlasIntelligence, str, str]]:
    """Fetch findings from all upstream MF agents (mf-rs-analyzer + mf-flow-analyzer).

    Returns a flat list of (finding, agent_id, finding_type) tuples.
    """
    mf_transitions = await list_findings(
        db=db,
        agent_id=_MF_RS_AGENT,
        finding_type=_MF_TRANSITION_TYPE,
        limit=lookback_limit,
    )
    mf_flow_reversals = await list_findings(
        db=db,
        agent_id=_MF_FLOW_AGENT,
        finding_type=_MF_FLOW_TYPE,
        limit=lookback_limit,
    )
    return [
        *((f, _MF_RS_AGENT, _MF_TRANSITION_TYPE) for f in mf_transitions),
        *((f, _MF_FLOW_AGENT, _MF_FLOW_TYPE) for f in mf_flow_reversals),
    ]


async def run(
    db: AsyncSession,
    data_as_of: datetime,
    lookback_limit: int = 200,
) -> dict[str, int]:
    """Main entry point for the MF decisions generator agent.

    Reads recent findings from mf-rs-analyzer and mf-flow-analyzer agents,
    maps them to decisions, and writes to atlas_decisions (idempotent).

    Args:
        db: Async SQLAlchemy session.
        data_as_of: Timezone-aware datetime. Must not be naive.
        lookback_limit: Maximum findings to read per finding type.

    Returns:
        dict with keys: findings_read, decisions_written, decisions_skipped

    Raises:
        ValueError: If data_as_of is a naive datetime (no tzinfo).
    """
    if data_as_of.tzinfo is None:
        raise ValueError("data_as_of must be timezone-aware (IST or UTC)")

    data_as_of_date = data_as_of.date()
    log.info("mf_decisions_generator_start", data_as_of=str(data_as_of))

    all_findings = await _fetch_all_findings(db, lookback_limit)
    findings_read = len(all_findings)
    decisions_written = 0
    decisions_skipped = 0

    for finding, agent_id, finding_type in all_findings:
        mapper = _FINDING_MAPPERS.get((agent_id, finding_type))
        if mapper is None:
            log.warning("no_mapper_for_finding", agent_id=agent_id, finding_type=finding_type)
            decisions_skipped += 1
            continue

        mapping = mapper(finding)
        if mapping is None:
            decisions_skipped += 1
            continue

        decision_type, confidence, invalidation_conditions = mapping
        written = await _write_decision(
            db=db,
            finding=finding,
            decision_type=decision_type,
            confidence=confidence,
            invalidation_conditions=invalidation_conditions,
            data_as_of_date=data_as_of_date,
        )
        if written:
            decisions_written += 1
        else:
            decisions_skipped += 1

    if decisions_written > 0:
        await db.commit()

    log.info(
        "mf_decisions_generator_complete",
        findings_read=findings_read,
        decisions_written=decisions_written,
        decisions_skipped=decisions_skipped,
    )
    return {
        "findings_read": findings_read,
        "decisions_written": decisions_written,
        "decisions_skipped": decisions_skipped,
    }
