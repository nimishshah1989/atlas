"""Unit tests for backend/services/rrg_service.py.

Tests cover:
  - _rrg_quadrant: 4 quadrant cases
  - _norm_rs: normalisation centres at 100
  - stddev=0 guard
  - tail building (up to 4 weekly points)
  - 503 when no sector RS data

All DB interactions are mocked with AsyncMock. No real DB calls.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.models.schemas import Quadrant
from backend.services.rrg_service import (
    _build_tail,
    _norm_rs,
    _rrg_quadrant,
    compute_sector_rrg,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mapping_all_result(rows: list[dict[str, Any]]) -> MagicMock:
    """Mock execute result returning .mappings().all() = rows."""
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _make_sector_row(
    sector: str = "Technology",
    rs_composite: float = 100.0,
    rs_composite_lag: float = 100.0,
    raw_momentum: float = 0.0,
    mean_rs: float = 100.0,
    stddev_rs: float = 5.0,
    pct_above_50dma: float | None = 65.0,
    breadth_regime: str | None = "BULL",
    as_of: datetime.date | None = None,
) -> dict[str, Any]:
    """Build a minimal sector row matching the main SQL output columns."""
    return {
        "sector": sector,
        "rs_composite": rs_composite,
        "rs_composite_lag": rs_composite_lag,
        "raw_momentum": raw_momentum,
        "mean_rs": mean_rs,
        "stddev_rs": stddev_rs,
        "pct_above_50dma": pct_above_50dma,
        "breadth_regime": breadth_regime,
        "as_of": as_of or datetime.date(2026, 4, 17),
    }


def _make_tail_row(sector: str, date: datetime.date, rs_composite: float) -> dict[str, Any]:
    """Build a tail row matching the tail SQL output columns."""
    return {"sector": sector, "date": date, "rs_composite": rs_composite}


def _make_session_with_two_results(
    main_rows: list[dict[str, Any]],
    tail_rows: list[dict[str, Any]],
) -> AsyncMock:
    """Create a session mock returning main rows then tail rows on consecutive execute() calls."""
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _mapping_all_result(main_rows),
            _mapping_all_result(tail_rows),
        ]
    )
    return session


# ---------------------------------------------------------------------------
# _rrg_quadrant tests (quadrant classification)
# ---------------------------------------------------------------------------


def test_rrg_quadrant_leading() -> None:
    """rs_score >= 100 AND rs_momentum >= 0 → LEADING."""
    result = _rrg_quadrant(Decimal("105"), Decimal("2.0"))
    assert result == Quadrant.LEADING, f"Expected LEADING, got {result}"


def test_rrg_quadrant_lagging() -> None:
    """rs_score < 100 AND rs_momentum < 0 → LAGGING."""
    result = _rrg_quadrant(Decimal("95"), Decimal("-1.5"))
    assert result == Quadrant.LAGGING, f"Expected LAGGING, got {result}"


def test_rrg_quadrant_improving() -> None:
    """rs_score < 100 AND rs_momentum >= 0 → IMPROVING."""
    result = _rrg_quadrant(Decimal("97"), Decimal("1.0"))
    assert result == Quadrant.IMPROVING, f"Expected IMPROVING, got {result}"


def test_rrg_quadrant_weakening() -> None:
    """rs_score >= 100 AND rs_momentum < 0 → WEAKENING."""
    result = _rrg_quadrant(Decimal("103"), Decimal("-0.5"))
    assert result == Quadrant.WEAKENING, f"Expected WEAKENING, got {result}"


def test_rrg_quadrant_boundary_at_100_score_positive_momentum() -> None:
    """Exactly rs_score=100 AND rs_momentum=0 → LEADING (>= boundary)."""
    result = _rrg_quadrant(Decimal("100"), Decimal("0"))
    assert result == Quadrant.LEADING


def test_rrg_quadrant_boundary_at_100_score_negative_momentum() -> None:
    """Exactly rs_score=100 AND rs_momentum=-0.001 → WEAKENING."""
    result = _rrg_quadrant(Decimal("100"), Decimal("-0.001"))
    assert result == Quadrant.WEAKENING


# ---------------------------------------------------------------------------
# _norm_rs tests
# ---------------------------------------------------------------------------


def test_rrg_normalize_centers_at_100() -> None:
    """3 sectors with rs_composite=95, 100, 105 and stddev≈5.

    After normalisation:
      - sector at mean (100) → rs_score ≈ 100
      - sector 1 stddev above (105) → rs_score ≈ 110
      - sector 1 stddev below (95)  → rs_score ≈ 90
    """
    mean = Decimal("100")
    stddev = Decimal("5")

    score_low = _norm_rs(Decimal("95"), mean, stddev)
    score_mid = _norm_rs(Decimal("100"), mean, stddev)
    score_high = _norm_rs(Decimal("105"), mean, stddev)

    # Middle should be exactly 100
    assert score_mid == Decimal("100"), f"Middle sector must be exactly 100, got {score_mid}"

    # Upper should be 110, lower should be 90
    assert score_high == Decimal("110"), f"Upper sector must be 110, got {score_high}"
    assert score_low == Decimal("90"), f"Lower sector must be 90, got {score_low}"

    # Confirm ordering
    assert score_low < score_mid < score_high


def test_rrg_normalize_formula() -> None:
    """Verify formula: (rs - mean) / stddev * 10 + 100."""
    rs_raw = Decimal("120")
    mean = Decimal("100")
    stddev = Decimal("10")
    expected = (rs_raw - mean) / stddev * Decimal("10") + Decimal("100")
    result = _norm_rs(rs_raw, mean, stddev)
    assert result == expected


# ---------------------------------------------------------------------------
# stddev=0 guard test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rrg_stddev_zero_guard() -> None:
    """All sectors with identical rs_composite → stddev treated as 1, no ZeroDivisionError.

    All sectors at rs_composite=100, mean=100, stddev_samp=0 from DB.
    Service should set stddev_rs=1 and return valid RRGSectors.
    """
    main_rows = [
        _make_sector_row(
            sector=f"Sector{i}",
            rs_composite=100.0,
            rs_composite_lag=100.0,
            raw_momentum=0.0,
            mean_rs=100.0,
            stddev_rs=0.0,  # All sectors identical → STDDEV_SAMP = 0
        )
        for i in range(3)
    ]

    session = _make_session_with_two_results(main_rows, [])
    response = await compute_sector_rrg(benchmark="NIFTY 50", db=session)

    assert response is not None
    assert len(response.sectors) == 3
    # When stddev=0 → treated as 1; all rs_scores = (100-100)/1*10+100 = 100
    for sector in response.sectors:
        assert sector.rs_score == Decimal("100"), (
            f"With stddev=0 guard, rs_score should be 100.0 for all sectors, got {sector.rs_score}"
        )
    # Response must include stddev_rs = 1 (the guard value)
    assert response.stddev_rs == Decimal("1"), (
        f"stddev_rs must be Decimal('1') when original is 0, got {response.stddev_rs}"
    )


# ---------------------------------------------------------------------------
# Tail tests
# ---------------------------------------------------------------------------


def test_rrg_tail_returns_up_to_4_weekly_points() -> None:
    """_build_tail with 4 weekly rows for a sector → 4 RRGPoints.

    Each rs_score should be normalised. The oldest point gets rs_momentum=0.
    """
    today = datetime.date(2026, 4, 17)
    tail_rows = [
        _make_tail_row("Technology", today, 102.0),
        _make_tail_row("Technology", today - datetime.timedelta(days=7), 101.0),
        _make_tail_row("Technology", today - datetime.timedelta(days=14), 100.0),
        _make_tail_row("Technology", today - datetime.timedelta(days=21), 99.0),
    ]
    mean_rs = Decimal("100")
    stddev_rs = Decimal("5")

    points = _build_tail("Technology", tail_rows, mean_rs, stddev_rs)

    assert len(points) == 4, f"Expected 4 tail points, got {len(points)}"

    # Oldest point (index 3) should have rs_momentum = 0
    assert points[3].rs_momentum == Decimal("0"), (
        f"Oldest tail point must have rs_momentum=0, got {points[3].rs_momentum}"
    )

    # All points should be normalised (not raw rs_composite values)
    # raw 102 → (102-100)/5*10+100 = 4+100 = 104
    from backend.services.rrg_service import _norm_rs as norm

    expected_newest = norm(Decimal("102"), mean_rs, stddev_rs)
    assert points[0].rs_score == expected_newest, (
        f"Newest point rs_score must be {expected_newest}, got {points[0].rs_score}"
    )


def test_rrg_tail_empty_when_no_rows() -> None:
    """_build_tail with no rows → empty list."""
    points = _build_tail("Technology", [], Decimal("100"), Decimal("5"))
    assert points == []


def test_rrg_tail_single_row_momentum_zero() -> None:
    """_build_tail with 1 row → 1 point with rs_momentum=0."""
    today = datetime.date(2026, 4, 17)
    tail_rows = [_make_tail_row("Energy", today, 98.0)]
    points = _build_tail("Energy", tail_rows, Decimal("100"), Decimal("5"))
    assert len(points) == 1
    assert points[0].rs_momentum == Decimal("0")


# ---------------------------------------------------------------------------
# 503 when no sector RS data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rrg_503_when_no_sector_rs() -> None:
    """Empty main query result → HTTPException(503)."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_mapping_all_result([]))

    with pytest.raises(HTTPException) as exc_info:
        await compute_sector_rrg(benchmark="NIFTY 50", db=session)

    assert exc_info.value.status_code == 503
    assert "not available" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_rrg_503_when_db_query_fails() -> None:
    """DB exception on main query → HTTPException(503)."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("DB is down"))

    with pytest.raises(HTTPException) as exc_info:
        await compute_sector_rrg(benchmark="NIFTY 50", db=session)

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Integration-style tests (full response structure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rrg_response_structure_with_valid_data() -> None:
    """Valid DB data → RRGResponse with correct structure."""
    today = datetime.date(2026, 4, 17)
    main_rows = [
        _make_sector_row("Technology", 105.0, 100.0, 5.0, 100.0, 5.0, 70.0, "BULL", today),
        _make_sector_row("Banking", 95.0, 98.0, -3.0, 100.0, 5.0, 45.0, "BEAR", today),
        _make_sector_row("Energy", 100.0, 100.0, 0.0, 100.0, 5.0, None, None, today),
    ]
    tail_rows = [
        _make_tail_row("Technology", today, 105.0),
        _make_tail_row("Technology", today - datetime.timedelta(days=7), 103.0),
    ]

    session = _make_session_with_two_results(main_rows, tail_rows)
    response = await compute_sector_rrg(benchmark="NIFTY 50", db=session)

    assert len(response.sectors) == 3
    assert response.mean_rs == Decimal("100")
    assert response.stddev_rs == Decimal("5")
    assert response.as_of == today
    assert response.meta.record_count == 3

    # Technology: rs_composite=105, mean=100, stddev=5 → (105-100)/5*10+100=110
    tech = next(s for s in response.sectors if s.sector == "Technology")
    assert tech.rs_score == Decimal("110")
    assert tech.quadrant == Quadrant.LEADING
    assert tech.pct_above_50dma == Decimal("70.0")
    assert len(tech.tail) == 2

    # Banking: rs_composite=95, mean=100, stddev=5 → (95-100)/5*10+100=90
    banking = next(s for s in response.sectors if s.sector == "Banking")
    assert banking.rs_score == Decimal("90")
    assert banking.quadrant == Quadrant.LAGGING

    # Energy: pct_above_50dma=None, breadth_regime=None
    energy = next(s for s in response.sectors if s.sector == "Energy")
    assert energy.pct_above_50dma is None
    assert energy.breadth_regime is None


@pytest.mark.asyncio
async def test_rrg_tail_fallback_empty_on_query_failure() -> None:
    """When tail query fails, sectors are still returned with empty tails."""
    today = datetime.date(2026, 4, 17)
    main_rows = [
        _make_sector_row("Technology", 105.0, 100.0, 5.0, 100.0, 5.0, 70.0, "BULL", today),
    ]

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _mapping_all_result(main_rows),
            RuntimeError("Tail query failed"),
        ]
    )

    response = await compute_sector_rrg(benchmark="NIFTY 50", db=session)
    assert len(response.sectors) == 1
    # Tail should be empty due to query failure
    assert response.sectors[0].tail == []
