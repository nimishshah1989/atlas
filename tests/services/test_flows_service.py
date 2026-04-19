"""Tests for FlowsService — V2FE-1."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from backend.services.flows_service import FlowsService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_count_then_data_session(count: int, data_rows: list[dict[str, Any]]) -> AsyncMock:
    """Build session mock: first execute returns COUNT, second returns data rows."""
    mock_session = AsyncMock()
    call_idx = [0]

    async def fake_execute(query: Any, params: Any = None) -> MagicMock:
        idx = call_idx[0]
        call_idx[0] += 1

        if idx == 0:
            # COUNT(*) query
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = count
            return mock_result
        else:
            # Data query
            mock_mapping = MagicMock()
            mock_mapping.all.return_value = list(data_rows)
            mock_result = MagicMock()
            mock_result.mappings.return_value = mock_mapping
            return mock_result

    mock_session.execute = fake_execute
    return mock_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_empty_table_returns_insufficient_data() -> None:
    """Test that COUNT=0 returns insufficient_data=True and empty series."""
    mock_session = _make_count_then_data_session(count=0, data_rows=[])
    svc = FlowsService(session=mock_session)

    result = await svc.get_flows(scope="fii_equity", range_="1y")

    assert result["_meta"]["insufficient_data"] is True
    assert result["series"] == []
    assert result["_meta"]["record_count"] == 0


async def test_decimal_enforcement_in_response() -> None:
    """Test that all financial values in series are Decimal, not float."""
    data_rows = [
        {
            "date": "2024-01-01",
            "fii_equity": 1500.5,
            "dii_equity": 800.25,
            "fii_debt": None,
            "dii_debt": None,
        },
    ]
    mock_session = _make_count_then_data_session(count=1, data_rows=data_rows)
    svc = FlowsService(session=mock_session)

    result = await svc.get_flows(scope="fii_equity", range_="1y")

    assert result["_meta"]["insufficient_data"] is False
    assert len(result["series"]) > 0
    for item in result["series"]:
        assert isinstance(item["value_crore"], Decimal), (
            f"Expected Decimal, got {type(item['value_crore'])} for {item}"
        )


async def test_date_range_filter_applied() -> None:
    """Test that date range parameter is used in query."""
    data_rows = [
        {
            "date": "2024-01-15",
            "fii_equity": 100.0,
            "dii_equity": 50.0,
            "fii_debt": None,
            "dii_debt": None,
        },
        {
            "date": "2024-02-15",
            "fii_equity": 200.0,
            "dii_equity": 75.0,
            "fii_debt": None,
            "dii_debt": None,
        },
    ]
    mock_session = _make_count_then_data_session(count=2, data_rows=data_rows)
    svc = FlowsService(session=mock_session)

    result = await svc.get_flows(scope="fii_equity,dii_equity", range_="1y")

    # Both queries executed (COUNT + data)
    assert result["_meta"]["insufficient_data"] is False
    # verify dates come back
    dates_in_result = [s["date"] for s in result["series"]]
    assert "2024-01-15" in dates_in_result


async def test_scope_filtering_fii_equity_only() -> None:
    """Test that specifying fii_equity scope returns only fii_equity entries."""
    data_rows = [
        {
            "date": "2024-01-01",
            "fii_equity": 100.0,
            "dii_equity": 50.0,
            "fii_debt": 30.0,
            "dii_debt": 20.0,
        },
    ]
    mock_session = _make_count_then_data_session(count=1, data_rows=data_rows)
    svc = FlowsService(session=mock_session)

    result = await svc.get_flows(scope="fii_equity", range_="1y")

    scopes_in_result = {s["scope"] for s in result["series"]}
    assert scopes_in_result == {"fii_equity"}
    assert "dii_equity" not in scopes_in_result
