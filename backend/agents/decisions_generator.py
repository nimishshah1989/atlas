"""Decisions Generator Agent — reads findings from atlas_intelligence and writes decisions.

Spec §23.2: Downstream consumer of rs-analyzer and sector-analyst findings.
Maps finding_type + quadrant/divergence data to buy_signal / sell_signal / overweight / avoid
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

AGENT_ID = "decisions-generator"
AGENT_TYPE = "computation"

# Horizon days for all V1 decisions
HORIZON_DAYS = 20
HORIZON_LABEL = "20_days"

# Confidence scores per mapping
_CONF_STRONG = Decimal("0.85")
_CONF_MEDIUM = Decimal("0.80")
_CONF_WEAK = Decimal("0.75")
_CONF_WEAKER = Decimal("0.70")

# Source agents we consume findings from
_RS_AGENT = "rs-analyzer"
_SECTOR_AGENT = "sector-analyst"

# Finding types we consume
_EQUITY_FINDING_TYPES = ("quadrant_classification", "quadrant_transition")
_SECTOR_FINDING_TYPES = ("sector_rotation", "breadth_divergence")


# ---------------------------------------------------------------------------
# Mapping helpers — each returns (decision_type, confidence, invalidation_conditions)
# or None if the finding should be skipped (e.g., neutral quadrant on first run).
# ---------------------------------------------------------------------------


def _map_equity_quadrant(finding: AtlasIntelligence) -> tuple[str, Decimal, list[str]] | None:
    """Map a quadrant_classification finding to a decision."""
    evidence = finding.evidence or {}
    quadrant = evidence.get("quadrant", "")

    if quadrant == "LEADING":
        return ("buy_signal", _CONF_STRONG, ["quadrant != LEADING"])
    elif quadrant == "IMPROVING":
        return ("buy_signal", _CONF_WEAKER, ["quadrant not in [LEADING, IMPROVING]"])
    elif quadrant == "WEAKENING":
        return ("sell_signal", _CONF_WEAK, ["quadrant != WEAKENING"])
    elif quadrant == "LAGGING":
        return ("sell_signal", _CONF_MEDIUM, ["quadrant != LAGGING"])
    return None


def _map_equity_transition(finding: AtlasIntelligence) -> tuple[str, Decimal, list[str]] | None:
    """Map a quadrant_transition finding to a decision."""
    evidence = finding.evidence or {}
    quadrant = evidence.get("quadrant", "")

    if quadrant == "LEADING":
        return ("buy_signal", _CONF_STRONG, ["quadrant leaves LEADING"])
    elif quadrant == "IMPROVING":
        return ("buy_signal", _CONF_WEAKER, ["quadrant leaves IMPROVING"])
    elif quadrant == "WEAKENING":
        return ("sell_signal", _CONF_MEDIUM, ["quadrant leaves WEAKENING"])
    elif quadrant == "LAGGING":
        return ("sell_signal", _CONF_STRONG, ["quadrant leaves LAGGING"])
    return None


def _map_sector_rotation(finding: AtlasIntelligence) -> tuple[str, Decimal, list[str]] | None:
    """Map a sector_rotation finding to a decision."""
    evidence = finding.evidence or {}
    quadrant = evidence.get("quadrant", "")

    if quadrant == "LEADING":
        return ("overweight", _CONF_STRONG, ["sector leaves LEADING"])
    elif quadrant == "IMPROVING":
        return ("overweight", _CONF_WEAKER, ["sector leaves IMPROVING"])
    elif quadrant == "WEAKENING":
        return ("avoid", _CONF_MEDIUM, ["sector leaves WEAKENING"])
    elif quadrant == "LAGGING":
        return ("avoid", _CONF_STRONG, ["sector leaves LAGGING"])
    return None


def _map_breadth_divergence(finding: AtlasIntelligence) -> tuple[str, Decimal, list[str]] | None:
    """Map a breadth_divergence finding to a decision."""
    evidence = finding.evidence or {}
    divergence_type = evidence.get("divergence_type", "")

    if divergence_type == "bullish_rs_weak_breadth":
        return ("avoid", _CONF_WEAK, ["breadth improves above 50%"])
    elif divergence_type == "bearish_rs_strong_breadth":
        return ("overweight", _CONF_WEAKER, ["RS turns positive"])
    return None


# ---------------------------------------------------------------------------
# Finding-type dispatch map
# ---------------------------------------------------------------------------

_FINDING_MAPPERS = {
    (_RS_AGENT, "quadrant_classification"): _map_equity_quadrant,
    (_RS_AGENT, "quadrant_transition"): _map_equity_transition,
    (_SECTOR_AGENT, "sector_rotation"): _map_sector_rotation,
    (_SECTOR_AGENT, "breadth_divergence"): _map_breadth_divergence,
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
        entity_type=finding.entity_type or "equity",
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
        "decision_written",
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
    """Fetch findings from all upstream agents (rs-analyzer + sector-analyst).

    Returns a flat list of (finding, agent_id, finding_type) tuples.
    """
    equity_classification = await list_findings(
        db=db, agent_id=_RS_AGENT, finding_type="quadrant_classification", limit=lookback_limit
    )
    equity_transitions = await list_findings(
        db=db, agent_id=_RS_AGENT, finding_type="quadrant_transition", limit=lookback_limit
    )
    sector_rotations = await list_findings(
        db=db, agent_id=_SECTOR_AGENT, finding_type="sector_rotation", limit=lookback_limit
    )
    breadth_divergences = await list_findings(
        db=db, agent_id=_SECTOR_AGENT, finding_type="breadth_divergence", limit=lookback_limit
    )
    return [
        *((f, _RS_AGENT, "quadrant_classification") for f in equity_classification),
        *((f, _RS_AGENT, "quadrant_transition") for f in equity_transitions),
        *((f, _SECTOR_AGENT, "sector_rotation") for f in sector_rotations),
        *((f, _SECTOR_AGENT, "breadth_divergence") for f in breadth_divergences),
    ]


async def run(
    db: AsyncSession,
    data_as_of: datetime,
    lookback_limit: int = 200,
) -> dict[str, int]:
    """Main entry point for the decisions generator agent.

    Reads recent findings from rs-analyzer and sector-analyst agents,
    maps them to decisions, and writes to atlas_decisions (idempotent).

    Returns:
        dict with keys: findings_read, decisions_written, decisions_skipped
    """
    if data_as_of.tzinfo is None:
        raise ValueError("data_as_of must be timezone-aware (IST or UTC)")

    data_as_of_date = data_as_of.date()
    log.info("decisions_generator_start", data_as_of=str(data_as_of))

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
        "decisions_generator_complete",
        findings_read=findings_read,
        decisions_written=decisions_written,
        decisions_skipped=decisions_skipped,
    )
    return {
        "findings_read": findings_read,
        "decisions_written": decisions_written,
        "decisions_skipped": decisions_skipped,
    }
