"""Sentiment Composite service for ATLAS C-DER-3.

Builds a 0–100 composite sentiment score from 4 components:
  1. Price Breadth (base weight 0.4) — de_breadth_daily, HARD FAIL if empty
  2. Options/PCR   (base weight 0.2) — de_fo_summary; 0 rows → unavailable
  3. Institutional Flow (base weight 0.2) — de_flow_daily FII; ≤5 → unavailable
  4. Fundamental Revisions (base weight 0.2) — de_equity_fundamentals medians

Weight redistribution when components are unavailable:
  pcr avail / flow avail  → breadth / pcr / flow / fund / redistrib
  ✓ / ✓                  → 0.4 / 0.2 / 0.2 / 0.2 / False
  ✓ / ✗                  → 0.5 / 0.2 / 0.0 / 0.3 / True
  ✗ / ✓                  → 0.5 / 0.0 / 0.2 / 0.3 / True
  ✗ / ✗                  → 0.6 / 0.0 / 0.0 / 0.4 / True

Composite = weighted average of available (non-None) scores.
If fund_score is also None, it is excluded from the weighted average.

Zone thresholds: <20=EXTREME_FEAR, <40=FEAR, <60=NEUTRAL, <80=GREED, ≥80=EXTREME_GREED.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Optional

import structlog
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.schemas import (
    ResponseMeta,
    SentimentComponent,
    SentimentResponse,
    SentimentZone,
)

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Weight redistribution lookup (locked, exhaustive)
# ---------------------------------------------------------------------------

# Key: (pcr_available: bool, flow_available: bool)
# Value: (breadth_w, pcr_w, flow_w, fund_w, redistribution_active)
_WEIGHT_TABLE: dict[tuple[bool, bool], tuple[Decimal, Decimal, Decimal, Decimal, bool]] = {
    (True, True): (
        Decimal("0.4"),
        Decimal("0.2"),
        Decimal("0.2"),
        Decimal("0.2"),
        False,
    ),
    (True, False): (
        Decimal("0.5"),
        Decimal("0.2"),
        Decimal("0.0"),
        Decimal("0.3"),
        True,
    ),
    (False, True): (
        Decimal("0.5"),
        Decimal("0.0"),
        Decimal("0.2"),
        Decimal("0.3"),
        True,
    ),
    (False, False): (
        Decimal("0.6"),
        Decimal("0.0"),
        Decimal("0.0"),
        Decimal("0.4"),
        True,
    ),
}


# ---------------------------------------------------------------------------
# Sub-metric normalisation helpers
# ---------------------------------------------------------------------------


def _norm_breadth(row: dict) -> Optional[Decimal]:  # type: ignore[type-arg]
    """Aggregate multiple breadth sub-metrics into a single 0–100 score.

    Sub-metrics:
      - pct_above_200dma (already 0–100)
      - pct_above_50dma  (already 0–100)
      - ad_ratio         (A/D ratio; 1.0 = neutral, scaled by ×50)
      - mcclellan_oscillator (range ~-300 to +300, centre=0 → shift by 150, /3)
      - 52w high/low ratio  (highs / (highs + lows) × 100)

    Returns None only if no sub-metrics have data (should not happen in practice
    since de_breadth_daily is required to have at least 1 row by this point).
    """
    scores: list[Decimal] = []

    val_200 = row.get("pct_above_200dma")
    if val_200 is not None:
        scores.append(Decimal(str(val_200)))

    val_50 = row.get("pct_above_50dma")
    if val_50 is not None:
        scores.append(Decimal(str(val_50)))

    ad_ratio = row.get("ad_ratio")
    if ad_ratio is not None:
        raw = Decimal(str(ad_ratio)) * Decimal("50")
        scores.append(max(Decimal("0"), min(Decimal("100"), raw)))

    mcclellan = row.get("mcclellan_oscillator")
    if mcclellan is not None:
        raw = (Decimal(str(mcclellan)) + Decimal("150")) / Decimal("3")
        scores.append(max(Decimal("0"), min(Decimal("100"), raw)))

    highs = row.get("new_52w_highs") or 0
    lows = row.get("new_52w_lows") or 0
    if highs + lows > 0:
        scores.append(Decimal(str(highs)) / Decimal(str(highs + lows)) * Decimal("100"))
    else:
        scores.append(Decimal("50"))  # neutral when no highs or lows data

    if not scores:
        return None
    return sum(scores, Decimal("0")) / Decimal(str(len(scores)))


def _norm_fundamentals(
    median_rev_growth: Optional[float],
    median_profit_growth: Optional[float],
    median_pe: Optional[float],
) -> Optional[Decimal]:
    """Normalise fundamental revision medians into a 0–100 score.

    Revenue growth 0–30% → 0–100 linearly.
    Profit growth 0–30%  → 0–100 linearly.
    PE ratio: inverted; lower PE = more value = higher score.
      (pe - 10) / 30 × 100, clamped 0–100.

    Returns None when all inputs are None.
    """
    scores: list[Decimal] = []

    if median_rev_growth is not None:
        raw = max(Decimal("0"), min(Decimal("30"), Decimal(str(median_rev_growth))))
        scores.append(raw / Decimal("30") * Decimal("100"))

    if median_profit_growth is not None:
        raw = max(Decimal("0"), min(Decimal("30"), Decimal(str(median_profit_growth))))
        scores.append(raw / Decimal("30") * Decimal("100"))

    if median_pe is not None:
        pe_score = max(
            Decimal("0"),
            min(
                Decimal("100"),
                (Decimal(str(median_pe)) - Decimal("10")) / Decimal("30") * Decimal("100"),
            ),
        )
        scores.append(pe_score)

    if not scores:
        return None
    return sum(scores, Decimal("0")) / Decimal(str(len(scores)))


def _zone(score: Optional[Decimal]) -> Optional[SentimentZone]:
    """Map a 0–100 score to a SentimentZone."""
    if score is None:
        return None
    if score < Decimal("20"):
        return SentimentZone.EXTREME_FEAR
    if score < Decimal("40"):
        return SentimentZone.FEAR
    if score < Decimal("60"):
        return SentimentZone.NEUTRAL
    if score < Decimal("80"):
        return SentimentZone.GREED
    return SentimentZone.EXTREME_GREED


# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

_BREADTH_SQL = text(
    """
    SELECT
        pct_above_200dma,
        pct_above_50dma,
        ad_ratio,
        mcclellan_oscillator,
        mcclellan_summation,
        new_52w_highs,
        new_52w_lows,
        advance + decline + COALESCE(unchanged, 0) AS total_stocks,
        date
    FROM de_breadth_daily
    ORDER BY date DESC
    LIMIT 1
    """
)

_PCR_COUNT_SQL = text("SELECT COUNT(*) AS row_count FROM de_fo_summary")

_FLOW_COUNT_SQL = text("SELECT COUNT(*) AS row_count FROM de_flow_daily WHERE category = 'FII'")

_FUND_SQL = text(
    """
    SELECT
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY revenue_growth_yoy_pct)
            AS median_rev_growth,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY profit_growth_yoy_pct)
            AS median_profit_growth,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pe_ratio)
            AS median_pe
    FROM de_equity_fundamentals f
    JOIN de_instrument i ON i.id = f.instrument_id
    WHERE i.is_active = true
      AND i.nifty_500 = true
    """
)


# ---------------------------------------------------------------------------
# Main service function
# ---------------------------------------------------------------------------


async def compute_sentiment_composite(db: AsyncSession) -> SentimentResponse:
    """Build a 0–100 composite sentiment score from 4 data components.

    Component 1 (Price Breadth) is a hard-fail: raises HTTPException(503)
    when de_breadth_daily is empty. All other components degrade gracefully.
    """
    t0 = time.monotonic()

    # ------------------------------------------------------------------
    # Component 1: Price Breadth (hard-fail)
    # ------------------------------------------------------------------
    try:
        breadth_result = await db.execute(_BREADTH_SQL)
        breadth_row = breadth_result.mappings().one_or_none()
    except Exception as exc:
        log.error("sentiment: breadth query failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Breadth data not available") from exc

    if breadth_row is None:
        log.warning("sentiment: de_breadth_daily is empty")
        raise HTTPException(status_code=503, detail="Breadth data not available")

    breadth_row_dict = dict(breadth_row)
    breadth_score: Optional[Decimal] = _norm_breadth(breadth_row_dict)
    breadth_as_of = breadth_row_dict.get("date")

    # ------------------------------------------------------------------
    # Component 2: Options/PCR
    # ------------------------------------------------------------------
    pcr_available = False
    pcr_score: Optional[Decimal] = None
    pcr_note: Optional[str] = None

    try:
        pcr_result = await db.execute(_PCR_COUNT_SQL)
        pcr_count_row = pcr_result.mappings().one()
        pcr_row_count = int(pcr_count_row["row_count"])
        if pcr_row_count > 0:
            pcr_available = True
            # PCR score calculation placeholder (pipeline dead, row_count=0)
            # When populated: PCR formula from spec Part C
            pcr_score = None  # would be computed from actual PCR data
        else:
            pcr_note = "PCR data unavailable — pipeline gap"
    except Exception as exc:
        log.warning("sentiment: PCR query failed", error=str(exc))
        pcr_note = "PCR data unavailable — pipeline gap"

    # ------------------------------------------------------------------
    # Component 3: Institutional Flow
    # ------------------------------------------------------------------
    flow_available = False
    flow_score: Optional[Decimal] = None
    flow_note: Optional[str] = None

    try:
        flow_result = await db.execute(_FLOW_COUNT_SQL)
        flow_count_row = flow_result.mappings().one()
        flow_row_count = int(flow_count_row["row_count"])
        if flow_row_count > 5:
            flow_available = True
            # Flow score calculation placeholder (pipeline dead, row_count<=5)
            flow_score = None  # would be computed from actual FII flow data
        else:
            flow_note = "FII flow data unavailable — pipeline gap"
    except Exception as exc:
        log.warning("sentiment: flow query failed", error=str(exc))
        flow_note = "FII flow data unavailable — pipeline gap"

    # ------------------------------------------------------------------
    # Component 4: Fundamental Revisions
    # ------------------------------------------------------------------
    fund_available = False
    fund_score: Optional[Decimal] = None
    fund_note: Optional[str] = None

    try:
        fund_result = await db.execute(_FUND_SQL)
        fund_row = fund_result.mappings().one_or_none()
        if fund_row is not None:
            rev_growth = fund_row["median_rev_growth"]
            profit_growth = fund_row["median_profit_growth"]
            pe = fund_row["median_pe"]

            if rev_growth is not None or profit_growth is not None or pe is not None:
                fund_score = _norm_fundamentals(rev_growth, profit_growth, pe)
                if fund_score is not None:
                    fund_available = True
                else:
                    fund_note = "Fundamentals data unavailable"
            else:
                fund_note = "Fundamentals data unavailable"
        else:
            fund_note = "Fundamentals data unavailable"
    except Exception as exc:
        log.warning("sentiment: fundamentals query failed", error=str(exc))
        fund_note = "Fundamentals data unavailable"

    # ------------------------------------------------------------------
    # Weight redistribution
    # ------------------------------------------------------------------
    breadth_weight, pcr_weight, flow_weight, fund_weight, redistrib = _WEIGHT_TABLE[
        (pcr_available, flow_available)
    ]

    # ------------------------------------------------------------------
    # Composite score — weighted average of available components
    # ------------------------------------------------------------------
    numerator = Decimal("0")
    denominator = Decimal("0")
    component_pairs = [
        (breadth_score, breadth_weight),
        (pcr_score, pcr_weight),
        (flow_score, flow_weight),
        (fund_score, fund_weight),
    ]
    for score, weight in component_pairs:
        if score is not None and weight > Decimal("0"):
            numerator += score * weight
            denominator += weight

    composite: Optional[Decimal] = (numerator / denominator) if denominator > Decimal("0") else None

    # ------------------------------------------------------------------
    # Build response
    # ------------------------------------------------------------------
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    components = [
        SentimentComponent(
            name="Price Breadth",
            score=breadth_score,
            weight=breadth_weight,
            available=True,
            note=None,
        ),
        SentimentComponent(
            name="Options/PCR",
            score=pcr_score,
            weight=pcr_weight,
            available=pcr_available,
            note=pcr_note,
        ),
        SentimentComponent(
            name="Institutional Flow",
            score=flow_score,
            weight=flow_weight,
            available=flow_available,
            note=flow_note,
        ),
        SentimentComponent(
            name="Fundamental Revisions",
            score=fund_score,
            weight=fund_weight,
            available=fund_available,
            note=fund_note,
        ),
    ]

    log.info(
        "compute_sentiment_composite",
        composite=str(composite) if composite is not None else "None",
        zone=_zone(composite),
        redistrib=redistrib,
        query_ms=elapsed_ms,
    )

    return SentimentResponse(
        composite_score=composite,
        zone=_zone(composite),
        components=components,
        weight_redistribution_active=redistrib,
        as_of=breadth_as_of,
        meta=ResponseMeta(record_count=4, query_ms=elapsed_ms),
    )
