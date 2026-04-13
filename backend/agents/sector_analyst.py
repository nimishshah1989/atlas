"""Sector Analyst Agent — classify sectors into RRG quadrants, detect rotations and divergences.

Spec §6 AGENT 2: Reads sector rollups via JIPDataService.get_sector_rollups() (never direct
de_* SQL), computes quadrant classifications, detects sector rotations (quadrant changes) and
breadth-RS divergences, and writes findings to atlas_intelligence via store_finding.

This agent does NOT call any LLM. It is pure computation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.rs_analyzer import Quadrant, _to_decimal, classify_quadrant
from backend.clients.jip_data_service import JIPDataService
from backend.services.intelligence import list_findings, store_finding

log = structlog.get_logger(__name__)

AGENT_ID = "sector-analyst"
AGENT_TYPE = "computation"

# Confidence scores for findings
CONFIDENCE_QUADRANT = Decimal("0.80")
CONFIDENCE_ROTATION = Decimal("0.85")
CONFIDENCE_DIVERGENCE = Decimal("0.80")
CONFIDENCE_SUMMARY = Decimal("0.90")

_ZERO = Decimal("0")

# Breadth thresholds for divergence detection
_BREADTH_WEAK_THRESHOLD = Decimal("50")  # pct_above_200dma < 50% = weak breadth
_BREADTH_STRONG_THRESHOLD = Decimal("70")  # pct_above_200dma >= 70% = strong breadth


async def _get_prior_sector_quadrant(
    db: AsyncSession,
    sector: str,
) -> Quadrant | None:
    """Fetch the most recent quadrant finding for a sector from atlas_intelligence.

    Returns None if no prior finding exists (first run for this sector).
    """
    findings = await list_findings(
        db=db,
        entity=sector,
        agent_id=AGENT_ID,
        finding_type="sector_quadrant",
        limit=1,
    )
    if not findings:
        return None

    evidence = findings[0].evidence or {}
    quadrant_str = evidence.get("quadrant")
    if quadrant_str is None:
        return None

    try:
        return Quadrant(quadrant_str)
    except ValueError:
        log.warning("unknown_sector_quadrant_in_evidence", sector=sector, quadrant_str=quadrant_str)
        return None


async def _write_sector_quadrant_finding(
    db: AsyncSession,
    sector: str,
    quadrant: Quadrant,
    avg_rs_composite: Decimal,
    avg_rs_momentum: Decimal,
    stock_count: int,
    pct_above_200dma: Decimal | None,
    data_as_of: datetime,
) -> None:
    """Write/upsert the current sector quadrant classification."""
    breadth_str = f"{pct_above_200dma}%" if pct_above_200dma is not None else "N/A"
    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=sector,
        entity_type="sector",
        finding_type="sector_quadrant",
        title=f"{sector} sector in {quadrant.value} quadrant",
        content=(
            f"{sector} sector ({stock_count} stocks) is in the {quadrant.value} quadrant. "
            f"Avg RS composite: {avg_rs_composite}, avg RS momentum: {avg_rs_momentum}. "
            f"Breadth (% above 200dma): {breadth_str}."
        ),
        confidence=CONFIDENCE_QUADRANT,
        data_as_of=data_as_of,
        evidence={
            "quadrant": quadrant.value,
            "avg_rs_composite": str(avg_rs_composite),
            "avg_rs_momentum": str(avg_rs_momentum),
            "stock_count": stock_count,
            "pct_above_200dma": str(pct_above_200dma) if pct_above_200dma is not None else None,
        },
        tags=["sector", "quadrant", quadrant.value.lower(), sector.lower().replace(" ", "-")],
    )


async def _write_rotation_finding(
    db: AsyncSession,
    sector: str,
    quadrant: Quadrant,
    prior_quadrant: Quadrant,
    avg_rs_composite: Decimal,
    avg_rs_momentum: Decimal,
    stock_count: int,
    data_as_of: datetime,
) -> None:
    """Write a sector rotation finding when the sector changes quadrant."""
    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=sector,
        entity_type="sector",
        finding_type="sector_rotation",
        title=f"{sector} sector rotated from {prior_quadrant.value} to {quadrant.value}",
        content=(
            f"{sector} sector ({stock_count} stocks) has rotated from "
            f"{prior_quadrant.value} to {quadrant.value} quadrant. "
            f"Avg RS composite: {avg_rs_composite}, avg RS momentum: {avg_rs_momentum}."
        ),
        confidence=CONFIDENCE_ROTATION,
        data_as_of=data_as_of,
        evidence={
            "quadrant": quadrant.value,
            "prior_quadrant": prior_quadrant.value,
            "avg_rs_composite": str(avg_rs_composite),
            "avg_rs_momentum": str(avg_rs_momentum),
            "stock_count": stock_count,
        },
        tags=["rotation", "sector", quadrant.value.lower(), prior_quadrant.value.lower()],
    )


async def _write_breadth_divergence_finding(
    db: AsyncSession,
    sector: str,
    quadrant: Quadrant,
    avg_rs_composite: Decimal,
    pct_above_200dma: Decimal,
    stock_count: int,
    data_as_of: datetime,
    divergence_type: str,
) -> None:
    """Write a breadth-RS divergence finding."""
    if divergence_type == "bullish_rs_weak_breadth":
        description = (
            f"RS is positive (avg RS composite: {avg_rs_composite}) but breadth is weak "
            f"(only {pct_above_200dma}% of stocks above 200dma). "
            "This suggests RS leadership may not be broadly supported."
        )
    else:  # bearish_rs_strong_breadth
        description = (
            f"RS is negative (avg RS composite: {avg_rs_composite}) but breadth is strong "
            f"({pct_above_200dma}% of stocks above 200dma). "
            "This may indicate a sector recovering before RS turns positive."
        )

    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=sector,
        entity_type="sector",
        finding_type="breadth_divergence",
        title=f"{sector} sector: breadth-RS divergence ({divergence_type})",
        content=f"{sector} sector ({stock_count} stocks): {description}",
        confidence=CONFIDENCE_DIVERGENCE,
        data_as_of=data_as_of,
        evidence={
            "quadrant": quadrant.value,
            "avg_rs_composite": str(avg_rs_composite),
            "pct_above_200dma": str(pct_above_200dma),
            "divergence_type": divergence_type,
            "stock_count": stock_count,
        },
        tags=["divergence", "breadth", "sector", sector.lower().replace(" ", "-")],
    )


async def _write_sector_summary(
    db: AsyncSession,
    data_as_of: datetime,
    total_sectors: int,
    analyzed: int,
    skipped: int,
    rotations: int,
    divergences: int,
    findings_written: int,
) -> None:
    """Write the run summary finding."""
    coverage_pct = (analyzed / total_sectors * 100) if total_sectors > 0 else Decimal("0")
    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity="market",
        entity_type="summary",
        finding_type="analysis_summary",
        title=(
            f"Sector analysis: {analyzed} sectors classified, "
            f"{rotations} rotations, {divergences} divergences"
        ),
        content=(
            f"Sector analyst run complete. "
            f"Fetched: {total_sectors} sectors, analyzed: {analyzed}, skipped: {skipped}. "
            f"Rotations detected: {rotations}. "
            f"Breadth-RS divergences detected: {divergences}. "
            f"Data as of: {data_as_of.isoformat()}."
        ),
        confidence=CONFIDENCE_SUMMARY,
        data_as_of=data_as_of,
        evidence={
            "total_sectors": total_sectors,
            "analyzed": analyzed,
            "skipped": skipped,
            "rotations": rotations,
            "divergences": divergences,
            "findings_written": findings_written,
            "coverage_pct": str(round(Decimal(str(coverage_pct)), 2)),
        },
        tags=["summary", "sector-analysis"],
    )


def _detect_breadth_divergence(
    avg_rs_composite: Decimal,
    pct_above_200dma: Decimal | None,
) -> str | None:
    """Detect breadth-RS divergence type, or None if no divergence.

    Bullish RS, weak breadth: RS > 0 AND pct_above_200dma < 50%
    Bearish RS, strong breadth: RS <= 0 AND pct_above_200dma >= 70%
    """
    if pct_above_200dma is None:
        return None

    if avg_rs_composite > _ZERO and pct_above_200dma < _BREADTH_WEAK_THRESHOLD:
        return "bullish_rs_weak_breadth"
    elif avg_rs_composite <= _ZERO and pct_above_200dma >= _BREADTH_STRONG_THRESHOLD:
        return "bearish_rs_strong_breadth"
    return None


async def _process_sector(
    db: AsyncSession,
    sector_row: dict[str, Any],
    data_as_of: datetime,
) -> tuple[int, int, int]:
    """Process one sector row: classify, detect rotation and divergence, write findings.

    Returns:
        (findings_written, rotation_count, divergence_count) — each 0 or 1 (or 2 if both).
    """
    sector_name: str = sector_row["sector"]
    avg_rs_composite = _to_decimal(sector_row["avg_rs_composite"])
    avg_rs_momentum = _to_decimal(sector_row["avg_rs_momentum"])
    quadrant = classify_quadrant(avg_rs_composite, avg_rs_momentum)
    stock_count = int(sector_row.get("stock_count") or 0)
    pct_raw = sector_row.get("pct_above_200dma")
    pct_above_200dma = _to_decimal(pct_raw) if pct_raw is not None else None

    findings_written = 0
    rotation_count = 0
    divergence_count = 0

    # Always write/upsert the current sector quadrant classification
    await _write_sector_quadrant_finding(
        db=db,
        sector=sector_name,
        quadrant=quadrant,
        avg_rs_composite=avg_rs_composite,
        avg_rs_momentum=avg_rs_momentum,
        stock_count=stock_count,
        pct_above_200dma=pct_above_200dma,
        data_as_of=data_as_of,
    )
    findings_written += 1

    # Check for sector rotation (quadrant change from prior run)
    prior_quadrant = await _get_prior_sector_quadrant(db, sector_name)
    if prior_quadrant is not None and prior_quadrant != quadrant:
        rotation_count = 1
        await _write_rotation_finding(
            db=db,
            sector=sector_name,
            quadrant=quadrant,
            prior_quadrant=prior_quadrant,
            avg_rs_composite=avg_rs_composite,
            avg_rs_momentum=avg_rs_momentum,
            stock_count=stock_count,
            data_as_of=data_as_of,
        )
        findings_written += 1

    # Check for breadth-RS divergence
    divergence_type = _detect_breadth_divergence(avg_rs_composite, pct_above_200dma)
    if divergence_type is not None:
        divergence_count = 1
        await _write_breadth_divergence_finding(
            db=db,
            sector=sector_name,
            quadrant=quadrant,
            avg_rs_composite=avg_rs_composite,
            pct_above_200dma=pct_above_200dma,  # type: ignore[arg-type]
            stock_count=stock_count,
            data_as_of=data_as_of,
            divergence_type=divergence_type,
        )
        findings_written += 1

    return findings_written, rotation_count, divergence_count


async def run(
    db: AsyncSession,
    jip: JIPDataService,
    data_as_of: datetime,
) -> dict[str, int]:
    """Main entry point for the sector analyst agent.

    Reads sector rollups via JIP client, classifies quadrants, detects
    rotations and breadth-RS divergences, writes findings to atlas_intelligence.

    Returns:
        dict with keys: analyzed, rotations, divergences, findings_written
    """
    if data_as_of.tzinfo is None:
        raise ValueError("data_as_of must be timezone-aware (IST or UTC)")

    log.info("sector_analyst_start", data_as_of=str(data_as_of))
    sectors: list[dict[str, Any]] = await jip.get_sector_rollups()

    total_sectors = len(sectors)
    analyzed = skipped = rotations = divergences = findings_written = 0

    for sector_row in sectors:
        sector_name = sector_row.get("sector")
        if not sector_name:
            skipped += 1
            continue
        if sector_row.get("avg_rs_composite") is None or sector_row.get("avg_rs_momentum") is None:
            log.warning("sector_missing_rs_data", sector=sector_name)
            skipped += 1
            continue

        analyzed += 1
        fw, rc, dc = await _process_sector(db, sector_row, data_as_of)
        findings_written += fw
        rotations += rc
        divergences += dc

    await _write_sector_summary(
        db=db,
        data_as_of=data_as_of,
        total_sectors=total_sectors,
        analyzed=analyzed,
        skipped=skipped,
        rotations=rotations,
        divergences=divergences,
        findings_written=findings_written,
    )
    findings_written += 1

    log.info(
        "sector_analyst_complete",
        analyzed=analyzed,
        rotations=rotations,
        divergences=divergences,
        findings_written=findings_written,
    )
    return {
        "analyzed": analyzed,
        "rotations": rotations,
        "divergences": divergences,
        "findings_written": findings_written,
    }
