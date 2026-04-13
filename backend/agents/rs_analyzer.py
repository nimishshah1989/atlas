"""RS Analyzer Agent — classify equities into RRG quadrants and detect transitions.

Spec §6 AGENT 1: Reads JIP equity universe via JIPDataService (never direct de_* SQL),
computes quadrant classifications, detects transitions, and writes findings to
atlas_intelligence via store_finding.

This agent does NOT call any LLM. It is pure computation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.services.intelligence import list_findings, store_finding

log = structlog.get_logger(__name__)

AGENT_ID = "rs-analyzer"
AGENT_TYPE = "computation"

# Confidence scores for findings
CONFIDENCE_TRANSITION = Decimal("0.85")
CONFIDENCE_FIRST_RUN_NOTABLE = Decimal("0.75")
CONFIDENCE_SUMMARY = Decimal("0.90")

_ZERO = Decimal("0")


class Quadrant(str, Enum):
    """RRG quadrant classification (spec §4.2)."""

    LEADING = "LEADING"
    IMPROVING = "IMPROVING"
    WEAKENING = "WEAKENING"
    LAGGING = "LAGGING"


def classify_quadrant(rs_composite: Decimal, rs_momentum: Decimal) -> Quadrant:
    """Classify a single equity into an RRG quadrant.

    Spec §4.2 logic (strict > 0, not >= 0):
      LEADING   = rs_composite > 0 AND rs_momentum > 0
      IMPROVING = rs_composite < 0 AND rs_momentum > 0
      WEAKENING = rs_composite > 0 AND rs_momentum < 0
      LAGGING   = rs_composite < 0 AND rs_momentum < 0

    Zero boundary: treat 0 as negative (spec uses strict >).
    """
    composite_positive = rs_composite > _ZERO
    momentum_positive = rs_momentum > _ZERO

    if composite_positive and momentum_positive:
        return Quadrant.LEADING
    elif not composite_positive and momentum_positive:
        return Quadrant.IMPROVING
    elif composite_positive and not momentum_positive:
        return Quadrant.WEAKENING
    else:
        return Quadrant.LAGGING


def _is_notable_first_run(quadrant: Quadrant) -> bool:
    """On first run (no prior history), only write findings for notable quadrants.

    Notable = LEADING or IMPROVING (positive momentum — actionable signal).
    """
    return quadrant in (Quadrant.LEADING, Quadrant.IMPROVING)


async def _get_prior_quadrant(
    db: AsyncSession,
    symbol: str,
) -> Quadrant | None:
    """Fetch the most recent quadrant finding for a symbol from atlas_intelligence.

    Returns None if no prior finding exists (first run for this entity).
    Uses list_findings (ORM query on atlas_intelligence — not de_* SQL).
    """
    findings = await list_findings(
        db=db,
        entity=symbol,
        agent_id=AGENT_ID,
        finding_type="quadrant_classification",
        limit=1,
    )
    if not findings:
        return None

    # Extract quadrant from the most recent finding's evidence dict
    evidence = findings[0].evidence or {}
    quadrant_str = evidence.get("quadrant")
    if quadrant_str is None:
        return None

    try:
        return Quadrant(quadrant_str)
    except ValueError:
        log.warning("unknown_quadrant_in_evidence", symbol=symbol, quadrant_str=quadrant_str)
        return None


def _to_decimal(val: Any) -> Decimal:
    """Convert a value to Decimal safely — never float."""
    return val if isinstance(val, Decimal) else Decimal(str(val))


async def _write_first_run_finding(
    db: AsyncSession,
    symbol: str,
    quadrant: Quadrant,
    rs_composite: Decimal,
    rs_momentum: Decimal,
    company_name: str,
    sector: str,
    data_as_of: datetime,
) -> None:
    """Write a quadrant classification finding for an entity seen for the first time."""
    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=symbol,
        entity_type="equity",
        finding_type="quadrant_classification",
        title=f"{symbol} in {quadrant.value} quadrant",
        content=(
            f"{company_name} ({sector}) is in the {quadrant.value} quadrant. "
            f"RS composite: {rs_composite}, RS momentum: {rs_momentum}. "
            f"This is a first-run classification — no prior history available."
        ),
        confidence=CONFIDENCE_FIRST_RUN_NOTABLE,
        data_as_of=data_as_of,
        evidence={
            "quadrant": quadrant.value,
            "rs_composite": str(rs_composite),
            "rs_momentum": str(rs_momentum),
            "sector": sector,
            "is_first_run": True,
        },
        tags=["quadrant", quadrant.value.lower(), sector.lower()],
    )


async def _write_transition_finding(
    db: AsyncSession,
    symbol: str,
    quadrant: Quadrant,
    prior_quadrant: Quadrant,
    rs_composite: Decimal,
    rs_momentum: Decimal,
    company_name: str,
    sector: str,
    data_as_of: datetime,
) -> None:
    """Write a quadrant transition finding when an entity changes quadrant."""
    content = (
        f"{company_name} ({sector}) moved from {prior_quadrant.value} to "
        f"{quadrant.value} quadrant. "
        f"RS composite: {rs_composite}, RS momentum: {rs_momentum}. "
    )
    rs_crossed_zero = (
        rs_composite > _ZERO and prior_quadrant in (Quadrant.IMPROVING, Quadrant.LAGGING)
    ) or (rs_composite <= _ZERO and prior_quadrant in (Quadrant.LEADING, Quadrant.WEAKENING))
    if rs_crossed_zero:
        direction = "positive" if rs_composite > _ZERO else "negative"
        content += f"{symbol} RS turned {direction} this week. "

    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=symbol,
        entity_type="equity",
        finding_type="quadrant_transition",
        title=f"{symbol} transitioned to {quadrant.value} quadrant",
        content=content,
        confidence=CONFIDENCE_TRANSITION,
        data_as_of=data_as_of,
        evidence={
            "quadrant": quadrant.value,
            "prior_quadrant": prior_quadrant.value,
            "rs_composite": str(rs_composite),
            "rs_momentum": str(rs_momentum),
            "sector": sector,
            "rs_crossed_zero": rs_crossed_zero,
        },
        tags=["transition", "quadrant", quadrant.value.lower(), sector.lower()],
    )


async def _write_unchanged_finding(
    db: AsyncSession,
    symbol: str,
    quadrant: Quadrant,
    rs_composite: Decimal,
    rs_momentum: Decimal,
    company_name: str,
    sector: str,
    data_as_of: datetime,
) -> None:
    """Upsert an unchanged quadrant classification (idempotent refresh)."""
    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=symbol,
        entity_type="equity",
        finding_type="quadrant_classification",
        title=f"{symbol} in {quadrant.value} quadrant",
        content=(
            f"{company_name} ({sector}) remains in {quadrant.value} quadrant. "
            f"RS composite: {rs_composite}, RS momentum: {rs_momentum}."
        ),
        confidence=CONFIDENCE_FIRST_RUN_NOTABLE,
        data_as_of=data_as_of,
        evidence={
            "quadrant": quadrant.value,
            "rs_composite": str(rs_composite),
            "rs_momentum": str(rs_momentum),
            "sector": sector,
            "is_first_run": False,
        },
        tags=["quadrant", quadrant.value.lower(), sector.lower()],
    )


async def _write_summary(
    db: AsyncSession,
    data_as_of: datetime,
    total_fetched: int,
    analyzed: int,
    skipped: int,
    transitions: int,
    findings_written: int,
) -> None:
    """Write the run summary finding."""
    coverage_pct = (analyzed / total_fetched * 100) if total_fetched > 0 else 0.0
    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity="market",
        entity_type="summary",
        finding_type="analysis_summary",
        title=f"RS analysis: {analyzed} equities classified, {transitions} transitions",
        content=(
            f"RS analyzer run complete. "
            f"Fetched: {total_fetched} equities, analyzed: {analyzed}, skipped: {skipped}. "
            f"Transitions detected: {transitions}. "
            f"Data coverage: {coverage_pct:.1f}%. "
            f"Data as of: {data_as_of.isoformat()}."
        ),
        confidence=CONFIDENCE_SUMMARY,
        data_as_of=data_as_of,
        evidence={
            "total_fetched": total_fetched,
            "analyzed": analyzed,
            "skipped": skipped,
            "transitions": transitions,
            "findings_written": findings_written,
            "coverage_pct": str(round(Decimal(str(coverage_pct)), 2)),
        },
        tags=["summary", "rs-analysis"],
    )


async def run(
    db: AsyncSession,
    jip: JIPDataService,
    data_as_of: datetime,
) -> dict[str, int]:
    """Main entry point for the RS analyzer agent.

    Reads equity universe via JIP client, classifies quadrants, detects
    transitions, and writes findings to atlas_intelligence.
    """
    if data_as_of.tzinfo is None:
        raise ValueError("data_as_of must be timezone-aware (IST or UTC)")

    log.info("rs_analyzer_start", data_as_of=str(data_as_of))
    equities: list[dict[str, Any]] = await jip.get_equity_universe(benchmark="NIFTY 500")

    total_fetched = len(equities)
    analyzed = 0
    skipped = 0
    transitions = 0
    findings_written = 0

    for equity in equities:
        symbol = equity.get("symbol")
        if not symbol:
            skipped += 1
            continue

        rs_composite_raw = equity.get("rs_composite")
        rs_momentum_raw = equity.get("rs_momentum")
        if rs_composite_raw is None or rs_momentum_raw is None:
            skipped += 1
            continue

        rs_composite = _to_decimal(rs_composite_raw)
        rs_momentum = _to_decimal(rs_momentum_raw)
        quadrant = classify_quadrant(rs_composite, rs_momentum)
        analyzed += 1

        prior_quadrant = await _get_prior_quadrant(db, symbol)
        company_name = equity.get("company_name", symbol)
        sector = equity.get("sector", "Unknown")
        common = dict(
            db=db,
            symbol=symbol,
            quadrant=quadrant,
            rs_composite=rs_composite,
            rs_momentum=rs_momentum,
            company_name=company_name,
            sector=sector,
            data_as_of=data_as_of,
        )

        if prior_quadrant is None:
            if _is_notable_first_run(quadrant):
                await _write_first_run_finding(**common)
                findings_written += 1
        elif prior_quadrant != quadrant:
            transitions += 1
            await _write_transition_finding(prior_quadrant=prior_quadrant, **common)
            findings_written += 1
        else:
            await _write_unchanged_finding(**common)
            findings_written += 1

    await _write_summary(
        db, data_as_of, total_fetched, analyzed, skipped, transitions, findings_written
    )
    findings_written += 1

    log.info(
        "rs_analyzer_complete",
        analyzed=analyzed,
        transitions=transitions,
        findings_written=findings_written,
    )
    return {"analyzed": analyzed, "transitions": transitions, "findings_written": findings_written}
