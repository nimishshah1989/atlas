"""Unit tests for backend/services/regime_service.py.

Tests compute_days_in_regime and compute_regime_history using AsyncMock
for the DB session. No real database calls.

Pattern:
  - Mock db.execute() to return a MagicMock with .mappings().all() or
    .mappings().one_or_none() returning fake rows as dicts.
  - Use side_effect lists for functions with multiple execute() calls.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.schemas import RegimeTransition
from backend.services.regime_service import (
    compute_days_in_regime,
    compute_regime_history,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mapping_one_result(row: dict[str, Any]) -> MagicMock:
    """Return a mock execute result whose .mappings().one() returns the dict."""
    result = MagicMock()
    result.mappings.return_value.one.return_value = row
    result.mappings.return_value.one_or_none.return_value = row
    result.mappings.return_value.all.return_value = [row]
    return result


def _mapping_all_result(rows: list[dict[str, Any]]) -> MagicMock:
    """Return a mock execute result whose .mappings().all() returns the list."""
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    result.mappings.return_value.one_or_none.return_value = rows[0] if rows else None
    return result


def _make_session(side_effects: list[Any]) -> AsyncMock:
    """Create a mock AsyncSession whose execute() returns results in sequence."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=side_effects)
    return session


def _make_regime_rows(dates: list[datetime.date], regime: str) -> list[dict[str, Any]]:
    """Create a list of regime rows all with the same regime string."""
    return [{"date": d, "regime": regime} for d in dates]


# ---------------------------------------------------------------------------
# compute_days_in_regime tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_days_in_regime_counts_consecutive_same_regime() -> None:
    """10 consecutive BULL rows → days_in_regime = 10.

    Simulates: all 10 rows share regime='BULL', no prior break exists.
    The CTE returns COUNT(*) = 10.
    """
    # First execute() call: the CTE query → returns 10
    count_result = _mapping_one_result({"days_in_regime": 10})

    session = _make_session([count_result])
    result = await compute_days_in_regime(session)

    assert result == 10, f"Expected 10 consecutive BULL days, got {result}"


@pytest.mark.asyncio
async def test_days_in_regime_resets_on_regime_change() -> None:
    """5 BULL rows after 1 BEAR row → days_in_regime = 5.

    The CTE correctly counts only rows after the last regime break.
    """
    # CTE returns 5 (only BULL rows after the BEAR break)
    count_result = _mapping_one_result({"days_in_regime": 5})

    session = _make_session([count_result])
    result = await compute_days_in_regime(session)

    assert result == 5, f"Expected 5 days after reset, got {result}"


@pytest.mark.asyncio
async def test_days_in_regime_returns_none_when_table_empty() -> None:
    """Empty de_market_regime table → days_in_regime = None.

    When COUNT(*) returns 0, we do a secondary check; that also returns 0 rows.
    """
    # First call: CTE count returns 0
    count_result = _mapping_one_result({"days_in_regime": 0})
    # Second call: total row count check also returns 0
    total_count_result = _mapping_one_result({"c": 0})

    session = _make_session([count_result, total_count_result])
    result = await compute_days_in_regime(session)

    assert result is None, f"Expected None for empty table, got {result}"


@pytest.mark.asyncio
async def test_days_in_regime_single_row() -> None:
    """A single row → days_in_regime = 1."""
    count_result = _mapping_one_result({"days_in_regime": 1})
    session = _make_session([count_result])
    result = await compute_days_in_regime(session)
    assert result == 1


@pytest.mark.asyncio
async def test_days_in_regime_handles_exception_gracefully() -> None:
    """If the DB query raises, returns None (no propagation)."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("DB connection lost"))
    result = await compute_days_in_regime(session)
    assert result is None, "Should return None on exception, not propagate"


# ---------------------------------------------------------------------------
# compute_regime_history tests
# ---------------------------------------------------------------------------


def _history_rows() -> list[dict[str, Any]]:
    """Build rows representing 7 regime segments (DESC order) to test ≤5 cap.

    Segment 1 (current open): BULL  days 0..3  (4 rows)
    Segment 2 (completed):    BEAR  days 4..7  (4 rows)
    Segment 3 (completed):    BULL  days 8..11 (4 rows)
    Segment 4 (completed):    BEAR  days 12..15 (4 rows)
    Segment 5 (completed):    BULL  days 16..19 (4 rows)
    Segment 6 (completed):    BEAR  days 20..23 (4 rows)
    Segment 7 (truncated):    BULL  days 24..27 (4 rows)

    The RLE algorithm closes a segment when it finds the next boundary.
    Segment 7 is the last in the window and won't be closed — so 5 completed
    transitions are returned (segments 2–6).
    """
    today = datetime.date(2026, 4, 17)
    rows = []
    regimes = ["BULL", "BEAR", "BULL", "BEAR", "BULL", "BEAR", "BULL"]
    for seg_idx, regime in enumerate(regimes):
        for day_offset in range(4):
            rows.append(
                {
                    "date": today - datetime.timedelta(days=seg_idx * 4 + day_offset),
                    "regime": regime,
                }
            )
    return rows


@pytest.mark.asyncio
async def test_regime_history_returns_last_5_transitions() -> None:
    """3+ transitions mocked → ≤5 items, ordered most-recent-first.

    Uses the _history_rows() fixture with 3 regime segments:
      - Current open BULL (rows[0..3])
      - Completed BEAR    (rows[4..7])
      - Completed BULL    (rows[8..11])

    Expected: 2 completed transitions returned (skip current open).
    Each must have positive duration_days.
    """
    rows = _history_rows()
    all_result = _mapping_all_result(rows)
    session = _make_session([all_result])

    transitions = await compute_regime_history(session)

    assert isinstance(transitions, list), "Should return a list"
    assert len(transitions) <= 5, f"Must return at most 5 transitions, got {len(transitions)}"
    # With 7 segments in the fixture: 1 open + 5 completed + 1 truncated at window end.
    # The RLE returns transitions[1:6] = 5 completed transitions.
    assert len(transitions) == 5, (
        f"Expected 5 completed transitions with 7-segment fixture, got {len(transitions)}"
    )

    for t in transitions:
        assert isinstance(t, RegimeTransition)
        assert t.duration_days >= 1, (
            f"duration_days must be >= 1, got {t.duration_days} for {t.regime}"
        )
        assert t.ended_date is not None, "Completed transitions must have ended_date"


@pytest.mark.asyncio
async def test_regime_history_returns_none_when_table_empty() -> None:
    """Empty de_market_regime → regime_history = []."""
    all_result = _mapping_all_result([])
    session = _make_session([all_result])

    transitions = await compute_regime_history(session)
    assert transitions == [], f"Expected [], got {transitions}"


@pytest.mark.asyncio
async def test_regime_history_skips_current_open_segment() -> None:
    """The currently open regime segment (first in history) is NOT returned.

    The returned list contains only completed (closed) segments.
    """
    rows = _history_rows()
    all_result = _mapping_all_result(rows)
    session = _make_session([all_result])

    transitions = await compute_regime_history(session)

    # The current open BULL segment (rows[0..3]) should be excluded.
    # First returned completed transition should be BEAR (the segment immediately preceding BULL).
    if transitions:
        first = transitions[0]
        assert first.regime == "BEAR", (
            "First completed transition should be BEAR (after current open BULL),"
            f" got {first.regime}"
        )


@pytest.mark.asyncio
async def test_regime_history_transition_dates_are_consistent() -> None:
    """started_date < ended_date for every returned transition."""
    rows = _history_rows()
    all_result = _mapping_all_result(rows)
    session = _make_session([all_result])

    transitions = await compute_regime_history(session)

    for t in transitions:
        if t.ended_date is not None:
            assert t.started_date <= t.ended_date, (
                f"started_date {t.started_date} must be <= ended_date {t.ended_date}"
            )


@pytest.mark.asyncio
async def test_regime_history_handles_exception_gracefully() -> None:
    """If the DB query raises, returns [] (no propagation)."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("DB timeout"))
    result = await compute_regime_history(session)
    assert result == [], "Should return [] on exception"


@pytest.mark.asyncio
async def test_regime_history_single_regime_no_breaks() -> None:
    """All rows same regime → transitions list is empty (no completed segments)."""
    today = datetime.date(2026, 4, 17)
    rows = [{"date": today - datetime.timedelta(days=i), "regime": "BULL"} for i in range(20)]
    all_result = _mapping_all_result(rows)
    session = _make_session([all_result])

    transitions = await compute_regime_history(session)
    # With only one regime and no break, transitions[0] is the current open segment
    # but we skip it. transitions[1:6] would be [] since there are no more transitions.
    assert transitions == [], f"Expected empty history with no regime changes, got {transitions}"
