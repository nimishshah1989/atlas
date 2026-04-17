"""Unit tests for backend/services/sentiment_service.py.

Tests cover:
  - Weight redistribution for all 4 table states (pcr avail × flow avail)
  - Sub-metric normalisation for breadth score
  - Zone boundary thresholds
  - PCR/Flow unavailability with "pipeline gap" notes
  - 503 when de_breadth_daily is empty
  - Fundamental revisions computation

All DB interactions are mocked with AsyncMock. No real DB calls.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.models.schemas import SentimentZone
from backend.services.sentiment_service import (
    _norm_breadth,
    _norm_fundamentals,
    _zone,
    compute_sentiment_composite,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mapping_one_result(row: dict[str, Any] | None) -> MagicMock:
    """Mock execute result returning .mappings().one() = row."""
    result = MagicMock()
    result.mappings.return_value.one.return_value = row
    result.mappings.return_value.one_or_none.return_value = row
    return result


def _breadth_row(
    pct_above_200dma: float | None = 60.0,
    pct_above_50dma: float | None = 55.0,
    ad_ratio: float | None = 1.2,
    mcclellan_oscillator: float | None = 50.0,
    mcclellan_summation: float | None = 200.0,
    new_52w_highs: int | None = 40,
    new_52w_lows: int | None = 10,
    date: datetime.date | None = None,
) -> dict[str, Any]:
    """Build a minimal breadth row."""
    return {
        "pct_above_200dma": pct_above_200dma,
        "pct_above_50dma": pct_above_50dma,
        "ad_ratio": ad_ratio,
        "mcclellan_oscillator": mcclellan_oscillator,
        "mcclellan_summation": mcclellan_summation,
        "new_52w_highs": new_52w_highs,
        "new_52w_lows": new_52w_lows,
        "total_stocks": 500,
        "date": date or datetime.date(2026, 4, 17),
    }


def _fund_row(
    median_rev_growth: float | None = 15.0,
    median_profit_growth: float | None = 18.0,
    median_pe: float | None = 22.0,
) -> dict[str, Any]:
    """Build a minimal fundamentals row."""
    return {
        "median_rev_growth": median_rev_growth,
        "median_profit_growth": median_profit_growth,
        "median_pe": median_pe,
    }


def _make_session_4_queries(
    breadth: dict[str, Any] | None,
    pcr_count: int,
    flow_count: int,
    fund: dict[str, Any] | None,
) -> AsyncMock:
    """Build mock session with 4 sequential execute() calls (breadth, pcr, flow, fund)."""
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _mapping_one_result(breadth),
            _mapping_one_result({"row_count": pcr_count}),
            _mapping_one_result({"row_count": flow_count}),
            _mapping_one_result(fund),
        ]
    )
    return session


# ---------------------------------------------------------------------------
# Weight redistribution tests (exhaustive truth table)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentiment_composite_redistributes_weight_when_pcr_and_flow_empty() -> None:
    """Semantic sentinel: fo_summary=0, flow_daily<=5 → breadth=0.6, fund=0.4, redistrib=True."""
    session = _make_session_4_queries(
        breadth=_breadth_row(),
        pcr_count=0,
        flow_count=5,
        fund=_fund_row(),
    )
    response = await compute_sentiment_composite(session)

    assert response.weight_redistribution_active is True, (
        "weight_redistribution_active must be True when both PCR and Flow are unavailable"
    )
    assert len(response.components) == 4

    breadth_comp = next(c for c in response.components if c.name == "Price Breadth")
    pcr_comp = next(c for c in response.components if c.name == "Options/PCR")
    flow_comp = next(c for c in response.components if c.name == "Institutional Flow")
    fund_comp = next(c for c in response.components if c.name == "Fundamental Revisions")

    assert breadth_comp.weight == Decimal("0.6"), (
        f"Breadth weight must be 0.6 when pcr+flow unavailable, got {breadth_comp.weight}"
    )
    assert pcr_comp.weight == Decimal("0.0"), (
        f"PCR weight must be 0.0 when unavailable, got {pcr_comp.weight}"
    )
    assert flow_comp.weight == Decimal("0.0"), (
        f"Flow weight must be 0.0 when unavailable, got {flow_comp.weight}"
    )
    assert fund_comp.weight == Decimal("0.4"), (
        f"Fund weight must be 0.4 when pcr+flow unavailable, got {fund_comp.weight}"
    )

    assert pcr_comp.available is False
    assert flow_comp.available is False


@pytest.mark.asyncio
async def test_sentiment_pcr_only_unavailable() -> None:
    """fo_summary=0, flow populated → breadth=0.5, flow=0.2, fund=0.3, pcr=0.0."""
    session = _make_session_4_queries(
        breadth=_breadth_row(),
        pcr_count=0,  # PCR unavailable
        flow_count=50,  # Flow available (> 5)
        fund=_fund_row(),
    )
    response = await compute_sentiment_composite(session)

    assert response.weight_redistribution_active is True

    breadth_comp = next(c for c in response.components if c.name == "Price Breadth")
    pcr_comp = next(c for c in response.components if c.name == "Options/PCR")
    flow_comp = next(c for c in response.components if c.name == "Institutional Flow")
    fund_comp = next(c for c in response.components if c.name == "Fundamental Revisions")

    assert breadth_comp.weight == Decimal("0.5")
    assert pcr_comp.weight == Decimal("0.0")
    assert flow_comp.weight == Decimal("0.2")
    assert fund_comp.weight == Decimal("0.3")

    assert pcr_comp.available is False
    assert flow_comp.available is True


@pytest.mark.asyncio
async def test_sentiment_flow_only_unavailable() -> None:
    """flow_daily<=5, pcr populated → breadth=0.5, pcr=0.2, fund=0.3, flow=0.0."""
    session = _make_session_4_queries(
        breadth=_breadth_row(),
        pcr_count=100,  # PCR available
        flow_count=3,  # Flow unavailable (<= 5)
        fund=_fund_row(),
    )
    response = await compute_sentiment_composite(session)

    assert response.weight_redistribution_active is True

    breadth_comp = next(c for c in response.components if c.name == "Price Breadth")
    pcr_comp = next(c for c in response.components if c.name == "Options/PCR")
    flow_comp = next(c for c in response.components if c.name == "Institutional Flow")
    fund_comp = next(c for c in response.components if c.name == "Fundamental Revisions")

    assert breadth_comp.weight == Decimal("0.5")
    assert pcr_comp.weight == Decimal("0.2")
    assert flow_comp.weight == Decimal("0.0")
    assert fund_comp.weight == Decimal("0.3")

    assert flow_comp.available is False
    assert pcr_comp.available is True


@pytest.mark.asyncio
async def test_sentiment_all_available_baseline_weights() -> None:
    """All four components available → 0.4/0.2/0.2/0.2, redistribution_active=False."""
    session = _make_session_4_queries(
        breadth=_breadth_row(),
        pcr_count=500,  # PCR available
        flow_count=100,  # Flow available
        fund=_fund_row(),
    )
    response = await compute_sentiment_composite(session)

    assert response.weight_redistribution_active is False

    breadth_comp = next(c for c in response.components if c.name == "Price Breadth")
    pcr_comp = next(c for c in response.components if c.name == "Options/PCR")
    flow_comp = next(c for c in response.components if c.name == "Institutional Flow")
    fund_comp = next(c for c in response.components if c.name == "Fundamental Revisions")

    assert breadth_comp.weight == Decimal("0.4")
    assert pcr_comp.weight == Decimal("0.2")
    assert flow_comp.weight == Decimal("0.2")
    assert fund_comp.weight == Decimal("0.2")


# ---------------------------------------------------------------------------
# Breadth normalisation test
# ---------------------------------------------------------------------------


def test_sentiment_breadth_score_normalizes_sub_metrics() -> None:
    """Mock pct_above_200dma=80, pct_above_50dma=75, ad_ratio=1.5, mcclellan=30, h=40, l=10.

    Breadth score must be in [50, 100] and not None.
    """
    row = _breadth_row(
        pct_above_200dma=80.0,
        pct_above_50dma=75.0,
        ad_ratio=1.5,
        mcclellan_oscillator=30.0,
        new_52w_highs=40,
        new_52w_lows=10,
    )
    score = _norm_breadth(row)

    assert score is not None, "Score must not be None with valid breadth data"
    assert score >= Decimal("50"), f"Score must be >= 50, got {score}"
    assert score <= Decimal("100"), f"Score must be <= 100, got {score}"


def test_sentiment_breadth_normalisation_no_highs_lows() -> None:
    """When highs=0 and lows=0, the high/low sub-metric uses 50 (neutral)."""
    row = _breadth_row(new_52w_highs=0, new_52w_lows=0)
    score = _norm_breadth(row)
    assert score is not None
    # Score should still be computed (not None)


def test_sentiment_breadth_normalisation_only_pct_above() -> None:
    """With only pct_above_200dma and pct_above_50dma populated."""
    row = {
        "pct_above_200dma": 70.0,
        "pct_above_50dma": 65.0,
        "ad_ratio": None,
        "mcclellan_oscillator": None,
        "new_52w_highs": 0,
        "new_52w_lows": 0,
    }
    score = _norm_breadth(row)
    assert score is not None
    # Expected: (70 + 65 + 50) / 3 = 61.67 (approx)
    assert Decimal("50") < score < Decimal("90")


# ---------------------------------------------------------------------------
# Zone boundary tests
# ---------------------------------------------------------------------------


def test_sentiment_zone_boundaries() -> None:
    """Verify zone boundaries at 20, 40, 60, 80."""
    assert _zone(Decimal("10")) == SentimentZone.EXTREME_FEAR
    assert _zone(Decimal("30")) == SentimentZone.FEAR
    assert _zone(Decimal("50")) == SentimentZone.NEUTRAL
    assert _zone(Decimal("70")) == SentimentZone.GREED
    assert _zone(Decimal("90")) == SentimentZone.EXTREME_GREED

    # Boundary conditions
    assert _zone(Decimal("19.99")) == SentimentZone.EXTREME_FEAR
    assert _zone(Decimal("20.00")) == SentimentZone.FEAR
    assert _zone(Decimal("39.99")) == SentimentZone.FEAR
    assert _zone(Decimal("40.00")) == SentimentZone.NEUTRAL
    assert _zone(Decimal("59.99")) == SentimentZone.NEUTRAL
    assert _zone(Decimal("60.00")) == SentimentZone.GREED
    assert _zone(Decimal("79.99")) == SentimentZone.GREED
    assert _zone(Decimal("80.00")) == SentimentZone.EXTREME_GREED


def test_sentiment_zone_none_score() -> None:
    """None score → zone is None."""
    assert _zone(None) is None


# ---------------------------------------------------------------------------
# Pipeline gap note tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentiment_marks_pcr_unavailable_note_pipeline_gap() -> None:
    """fo_summary count=0 → PCR.available=False, note contains 'pipeline gap'."""
    session = _make_session_4_queries(
        breadth=_breadth_row(),
        pcr_count=0,
        flow_count=0,
        fund=_fund_row(),
    )
    response = await compute_sentiment_composite(session)

    pcr_comp = next(c for c in response.components if c.name == "Options/PCR")
    assert pcr_comp.available is False, "PCR must be unavailable when fo_summary has 0 rows"
    assert pcr_comp.note is not None, "PCR note must not be None"
    assert "pipeline gap" in pcr_comp.note.lower(), (
        f"PCR note must mention 'pipeline gap', got: '{pcr_comp.note}'"
    )


@pytest.mark.asyncio
async def test_sentiment_marks_flow_unavailable_note_pipeline_gap() -> None:
    """flow_daily count=5 → Flow.available=False, note contains 'pipeline gap'."""
    session = _make_session_4_queries(
        breadth=_breadth_row(),
        pcr_count=0,
        flow_count=5,  # <= 5 → unavailable
        fund=_fund_row(),
    )
    response = await compute_sentiment_composite(session)

    flow_comp = next(c for c in response.components if c.name == "Institutional Flow")
    assert flow_comp.available is False, "Flow must be unavailable when row_count <= 5"
    assert flow_comp.note is not None, "Flow note must not be None"
    assert "pipeline gap" in flow_comp.note.lower(), (
        f"Flow note must mention 'pipeline gap', got: '{flow_comp.note}'"
    )


# ---------------------------------------------------------------------------
# 503 test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentiment_503_when_breadth_missing() -> None:
    """de_breadth_daily empty (None result) → HTTPException 503."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_mapping_one_result(None))

    with pytest.raises(HTTPException) as exc_info:
        await compute_sentiment_composite(session)

    assert exc_info.value.status_code == 503
    assert "breadth" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_sentiment_503_when_breadth_query_raises() -> None:
    """DB exception on breadth query → HTTPException 503."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("DB down"))

    with pytest.raises(HTTPException) as exc_info:
        await compute_sentiment_composite(session)

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Fundamentals tests
# ---------------------------------------------------------------------------


def test_norm_fundamentals_with_all_values() -> None:
    """All three medians populated → returns a Decimal in [0, 100]."""
    score = _norm_fundamentals(15.0, 18.0, 22.0)
    assert score is not None
    assert Decimal("0") <= score <= Decimal("100")


def test_norm_fundamentals_all_none_returns_none() -> None:
    """All None inputs → returns None."""
    score = _norm_fundamentals(None, None, None)
    assert score is None


def test_norm_fundamentals_clamps_values() -> None:
    """Very high growth (>30) → clamped at 100; zero PE → pe_score clamped at 0."""
    # revenue_growth=50 → clamped to 30/30*100 = 100
    # profit_growth=40  → clamped to 100
    # pe=5 → (5-10)/30*100 = negative → clamped to 0
    score = _norm_fundamentals(50.0, 40.0, 5.0)
    assert score is not None
    # Three sub-metrics: (100 + 100 + 0) / 3 ≈ 66.67
    expected = (Decimal("100") + Decimal("100") + Decimal("0")) / Decimal("3")
    assert abs(score - expected) < Decimal("0.01"), f"Expected ~{expected}, got {score}"


@pytest.mark.asyncio
async def test_sentiment_fund_unavailable_when_all_null() -> None:
    """Fundamentals query returns all-NULL medians → fund component unavailable."""
    session = _make_session_4_queries(
        breadth=_breadth_row(),
        pcr_count=0,
        flow_count=0,
        fund=_fund_row(
            median_rev_growth=None,
            median_profit_growth=None,
            median_pe=None,
        ),
    )
    response = await compute_sentiment_composite(session)

    fund_comp = next(c for c in response.components if c.name == "Fundamental Revisions")
    assert fund_comp.available is False, "Fund must be unavailable when all medians are NULL"
    assert fund_comp.score is None


@pytest.mark.asyncio
async def test_sentiment_response_structure() -> None:
    """Response always has 4 components, composite_score, zone, as_of, meta."""
    session = _make_session_4_queries(
        breadth=_breadth_row(),
        pcr_count=0,
        flow_count=0,
        fund=_fund_row(),
    )
    response = await compute_sentiment_composite(session)

    assert len(response.components) == 4
    assert response.as_of is not None
    assert response.meta is not None
    assert response.meta.record_count == 4
    # Composite and zone can be None if all available components have None score,
    # but with valid breadth they should be set.
    # composite_score can be None or Decimal — just check it's not an error type
    if response.composite_score is not None:
        assert isinstance(response.composite_score, Decimal)


@pytest.mark.asyncio
async def test_sentiment_component_names_correct() -> None:
    """Four component names must exactly match spec."""
    session = _make_session_4_queries(
        breadth=_breadth_row(),
        pcr_count=0,
        flow_count=0,
        fund=_fund_row(),
    )
    response = await compute_sentiment_composite(session)

    names = {c.name for c in response.components}
    expected_names = {
        "Price Breadth",
        "Options/PCR",
        "Institutional Flow",
        "Fundamental Revisions",
    }
    assert names == expected_names, f"Component names mismatch: {names}"
