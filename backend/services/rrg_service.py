"""Sector Relative Rotation Graph (RRG) service for ATLAS C-DER-3.

Provides compute_sector_rrg() which builds the RRG data for all sectors:
  - Normalised RS score centred at 100 (Z-score * 10 + 100)
  - RS momentum (today - 28-day lag)
  - RRG quadrant (LEADING / IMPROVING / WEAKENING / LAGGING)
  - 4-point weekly tail for each sector

Reads from:
  - de_rs_scores (entity_type='sector'): 212,692 rows filtered to ~31 per date
  - de_sector_breadth_daily: 127,584 rows, DISTINCT ON for latest per sector

No writes. No new tables. No new dependencies.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.schemas import (
    Quadrant,
    ResponseMeta,
    RRGPoint,
    RRGResponse,
    RRGSector,
)

log = structlog.get_logger(__name__)


def _rrg_quadrant(rs_score: Decimal, rs_momentum: Decimal) -> Quadrant:
    """Classify RRG quadrant based on 100-centred rs_score and momentum.

    Note: this uses 100 as the centre-line (NOT 0 like compute_quadrant in
    core.computations which centres on raw rs_composite).
    """
    if rs_score >= Decimal("100") and rs_momentum >= Decimal("0"):
        return Quadrant.LEADING
    if rs_score < Decimal("100") and rs_momentum >= Decimal("0"):
        return Quadrant.IMPROVING
    if rs_score >= Decimal("100") and rs_momentum < Decimal("0"):
        return Quadrant.WEAKENING
    return Quadrant.LAGGING


def _norm_rs(
    rs_raw: Decimal,
    mean_rs: Decimal,
    stddev_rs: Decimal,
) -> Decimal:
    """Normalise rs_composite to a 100-centred score.

    Formula: (rs_raw - mean_rs) / stddev_rs * 10 + 100
    stddev_rs must not be 0 (caller ensures this with the 0-guard).
    """
    return (rs_raw - mean_rs) / stddev_rs * Decimal("10") + Decimal("100")


_MAIN_SQL = text(
    """
    WITH latest_sector_date AS (
        SELECT MAX(date) AS d
        FROM de_rs_scores
        WHERE entity_type = 'sector'
    ),
    lag_date AS (
        SELECT MAX(date) AS d
        FROM de_rs_scores
        WHERE entity_type = 'sector'
          AND date <= (SELECT d FROM latest_sector_date) - INTERVAL '28 days'
    ),
    today_rs AS (
        SELECT DISTINCT ON (entity_id) entity_id AS sector, rs_composite
        FROM de_rs_scores
        WHERE entity_type = 'sector'
          AND date = (SELECT d FROM latest_sector_date)
        ORDER BY entity_id, rs_composite DESC
    ),
    lag_rs AS (
        SELECT DISTINCT ON (entity_id) entity_id AS sector, rs_composite AS rs_composite_lag
        FROM de_rs_scores
        WHERE entity_type = 'sector'
          AND date = (SELECT d FROM lag_date)
        ORDER BY entity_id, rs_composite DESC
    ),
    stats AS (
        SELECT
            AVG(rs_composite)       AS mean_rs,
            STDDEV_SAMP(rs_composite) AS stddev_rs
        FROM today_rs
    ),
    breadth_latest AS (
        SELECT DISTINCT ON (sector)
            sector, pct_above_50dma, breadth_regime
        FROM de_sector_breadth_daily
        ORDER BY sector, date DESC
    )
    SELECT
        t.sector,
        t.rs_composite,
        COALESCE(l.rs_composite_lag, t.rs_composite) AS rs_composite_lag,
        t.rs_composite - COALESCE(l.rs_composite_lag, t.rs_composite) AS raw_momentum,
        s.mean_rs,
        s.stddev_rs,
        b.pct_above_50dma,
        b.breadth_regime,
        (SELECT d FROM latest_sector_date) AS as_of
    FROM today_rs t
    LEFT JOIN lag_rs l ON l.sector = t.sector
    CROSS JOIN stats s
    LEFT JOIN breadth_latest b ON b.sector = t.sector
    """
)

_TAIL_SQL = text(
    """
    WITH target_dates AS (
        SELECT DISTINCT r.date
        FROM de_rs_scores r
        WHERE r.entity_type = 'sector'
          AND r.date IN (
              (SELECT MAX(date) FROM de_rs_scores WHERE entity_type = 'sector'),
              (SELECT MAX(date) FROM de_rs_scores
               WHERE entity_type = 'sector'
                 AND date <= (SELECT MAX(date) FROM de_rs_scores
                              WHERE entity_type = 'sector') - INTERVAL '7 days'),
              (SELECT MAX(date) FROM de_rs_scores
               WHERE entity_type = 'sector'
                 AND date <= (SELECT MAX(date) FROM de_rs_scores
                              WHERE entity_type = 'sector') - INTERVAL '14 days'),
              (SELECT MAX(date) FROM de_rs_scores
               WHERE entity_type = 'sector'
                 AND date <= (SELECT MAX(date) FROM de_rs_scores
                              WHERE entity_type = 'sector') - INTERVAL '21 days')
          )
    )
    SELECT entity_id AS sector, date, rs_composite
    FROM de_rs_scores
    WHERE entity_type = 'sector'
      AND date IN (SELECT date FROM target_dates)
    ORDER BY entity_id, date DESC
    """
)


def _build_tail(
    sector: str,
    tail_rows: list[dict[str, Any]],
    mean_rs: Decimal,
    stddev_rs: Decimal,
) -> list[RRGPoint]:
    """Build up to 4 weekly RRG tail points for a sector.

    Deduplicates by date (JIP tables may have duplicate rows per sector+date).
    Takes the first row per date (rows are ordered DESC by date from SQL).
    rs_momentum for each point = diff from the next-older point.
    Oldest point gets momentum = 0.
    """
    # Filter to this sector and deduplicate by date (keep first per date)
    seen_dates: set[Any] = set()
    deduped_rows: list[dict[str, Any]] = []
    for r in tail_rows:
        if r["sector"] == sector and r["date"] not in seen_dates:
            seen_dates.add(r["date"])
            deduped_rows.append(r)
            if len(deduped_rows) == 4:  # cap at 4 weekly points
                break

    # rows are already ordered DESC by date from SQL
    points: list[RRGPoint] = []
    for i, row in enumerate(deduped_rows):
        rs_raw = Decimal(str(row["rs_composite"]))
        rs_score = _norm_rs(rs_raw, mean_rs, stddev_rs)

        if i + 1 < len(deduped_rows):
            older_raw = Decimal(str(deduped_rows[i + 1]["rs_composite"]))
            older_score = _norm_rs(older_raw, mean_rs, stddev_rs)
            rs_momentum = rs_score - older_score
        else:
            rs_momentum = Decimal("0")

        points.append(
            RRGPoint(
                date=row["date"],
                rs_score=rs_score,
                rs_momentum=rs_momentum,
            )
        )
    return points


async def compute_sector_rrg(
    benchmark: str,  # accepted but not used to filter — all sectors returned
    db: AsyncSession,
) -> RRGResponse:
    """Build the full RRG dataset for all sectors.

    Raises HTTPException(503) when no sector RS data is available.
    The `benchmark` parameter is a placeholder for future filtering;
    currently all sectors are returned regardless of its value.
    """
    t0 = time.monotonic()

    # Step 1: fetch main rows (today + lag + stats + breadth)
    try:
        main_result = await db.execute(_MAIN_SQL)
        rows = main_result.mappings().all()
    except Exception as exc:
        log.error("compute_sector_rrg: main query failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Sector RS data not available") from exc

    if not rows:
        log.warning("compute_sector_rrg: no sector RS rows in de_rs_scores")
        raise HTTPException(status_code=503, detail="Sector RS data not available")

    # Step 2: extract mean/stddev; guard stddev=0
    mean_rs_raw = rows[0]["mean_rs"]
    stddev_raw = rows[0]["stddev_rs"]

    mean_rs = Decimal(str(mean_rs_raw)) if mean_rs_raw is not None else Decimal("100")
    stddev_rs = Decimal(str(stddev_raw)) if stddev_raw is not None else Decimal("1")
    if stddev_rs == Decimal("0"):
        stddev_rs = Decimal("1")  # guard: all sectors identical

    as_of_raw = rows[0]["as_of"]

    # Step 3: fetch tail rows for all sectors
    try:
        tail_result = await db.execute(_TAIL_SQL)
        tail_rows = [dict(r) for r in tail_result.mappings().all()]
    except Exception as exc:
        log.warning("compute_sector_rrg: tail query failed", error=str(exc))
        tail_rows = []

    # Step 4: build RRGSector objects
    rrg_sectors: list[RRGSector] = []
    for row in rows:
        sector_name: str = row["sector"]
        rs_raw = Decimal(str(row["rs_composite"]))
        rs_score = _norm_rs(rs_raw, mean_rs, stddev_rs)
        rs_momentum = Decimal(str(row["raw_momentum"]))

        pct_50dma_raw = row["pct_above_50dma"]
        pct_50dma = Decimal(str(pct_50dma_raw)) if pct_50dma_raw is not None else None

        breadth_regime_raw = row["breadth_regime"]
        breadth_regime: Optional[str] = (
            str(breadth_regime_raw) if breadth_regime_raw is not None else None
        )

        tail = _build_tail(sector_name, tail_rows, mean_rs, stddev_rs)

        rrg_sectors.append(
            RRGSector(
                sector=sector_name,
                rs_score=rs_score,
                rs_momentum=rs_momentum,
                quadrant=_rrg_quadrant(rs_score, rs_momentum),
                pct_above_50dma=pct_50dma,
                breadth_regime=breadth_regime,
                tail=tail,
            )
        )

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "compute_sector_rrg",
        sector_count=len(rrg_sectors),
        mean_rs=str(mean_rs),
        stddev_rs=str(stddev_rs),
        query_ms=elapsed_ms,
    )

    return RRGResponse(
        sectors=rrg_sectors,
        mean_rs=mean_rs,
        stddev_rs=stddev_rs,
        as_of=as_of_raw,
        meta=ResponseMeta(record_count=len(rrg_sectors), query_ms=elapsed_ms),
    )
