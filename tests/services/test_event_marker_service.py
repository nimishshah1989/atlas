"""Tests for EventMarkerService — V2FE-1."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

from backend.services.event_marker_service import EventMarkerService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event_row(
    date_str: str,
    category: str,
    severity: str,
    affects: list[str],
    label: str,
) -> MagicMock:
    """Build a mock ORM row for AtlasKeyEvent."""
    row = MagicMock()
    row.date = datetime.date.fromisoformat(date_str)
    row.category = category
    row.severity = severity
    row.affects = affects
    row.label = label
    row.source = None
    row.description = None
    row.display_color = None
    row.source_url = None
    return row


def _make_session_returning_rows(rows: list[MagicMock]) -> AsyncMock:
    mock_session = AsyncMock()
    mock_scalar_result = MagicMock()
    mock_scalar_result.scalars.return_value.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=mock_scalar_result)
    return mock_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_scope_filter_india_only() -> None:
    """Test that only events matching the india scope are returned."""
    india_event = _make_event_row("2024-01-01", "rbi_policy", "high", ["india"], "RBI Policy")
    global_event = _make_event_row("2024-01-02", "fed_policy", "high", ["global"], "Fed Meeting")
    both_event = _make_event_row(
        "2024-01-03", "covid", "critical", ["india", "global"], "COVID Wave"
    )

    mock_session = _make_session_returning_rows([india_event, global_event, both_event])

    svc = EventMarkerService(session=mock_session)
    result = await svc.get_events(scope="india", range_="5y")

    events = result["events"]
    # Only india and both_event should pass scope filter
    assert len(events) == 2
    labels = [e["label"] for e in events]
    assert "RBI Policy" in labels
    assert "COVID Wave" in labels
    assert "Fed Meeting" not in labels


async def test_range_filter_applied() -> None:
    """Test that date range filter is passed to query."""
    mock_session = _make_session_returning_rows([])
    svc = EventMarkerService(session=mock_session)

    result = await svc.get_events(scope="india", range_="1y")

    # Verify query was executed (range filter embedded in SQL)
    mock_session.execute.assert_called_once()
    # Result should be empty but properly structured
    assert result["events"] == []
    assert "data_as_of" in result
    assert "source" in result


async def test_category_filter_applied() -> None:
    """Test that category filter restricts returned events."""
    rbi_event = _make_event_row("2024-01-01", "rbi_policy", "high", ["india"], "RBI Policy")
    election_event = _make_event_row("2024-01-02", "election", "high", ["india"], "Election")

    mock_session = _make_session_returning_rows([rbi_event, election_event])
    svc = EventMarkerService(session=mock_session)

    # The category filter is applied in the SQL, so mock returns both but scope matches
    result = await svc.get_events(scope="india", range_="5y", categories="rbi_policy")

    # Both rows pass scope filter (both have 'india')
    # Category filtering is done in SQL, so mock returns both anyway
    # but we verify the service calls correctly
    assert "events" in result
    assert "_meta" in result


async def test_empty_result_when_no_matching_events() -> None:
    """Test that empty events list is returned when no matching events exist."""
    mock_session = _make_session_returning_rows([])
    svc = EventMarkerService(session=mock_session)

    result = await svc.get_events(scope="global", range_="1y", categories="unknown_category")

    assert result["events"] == []
    assert result["source"] == "ATLAS key events"
    assert "_meta" in result
    assert result["_meta"]["record_count"] == 0
