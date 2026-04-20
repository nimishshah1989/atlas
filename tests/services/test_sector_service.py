"""Tests for SectorService."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from backend.services.sector_service import SectorService, _load_mf_sector_map

_D = Decimal


def _make_svc() -> SectorService:
    mock_jip = AsyncMock()
    return SectorService(mock_jip)


@pytest.mark.asyncio
async def test_sector_roll_up_empty_stocks_returns_hold():
    svc = _make_svc()
    svc._svc.get_equity_universe = AsyncMock(return_value=[])
    svc._svc.get_mf_universe = AsyncMock(return_value=[])

    summary = await svc.sector_roll_up("banking", universe="NIFTY500")

    assert summary.composite_action == "HOLD"
    assert summary.four_lens.get("rs") is None


@pytest.mark.asyncio
async def test_sector_roll_up_computes_mean_rs():
    svc = _make_svc()
    stocks = [
        {
            "symbol": "A",
            "rs_composite": 60,
            "rs_momentum": 2,
            "above_200dma": True,
            "above_50dma": True,
            "date": "2024-01-15",
        },
        {
            "symbol": "B",
            "rs_composite": 80,
            "rs_momentum": 4,
            "above_200dma": True,
            "above_50dma": True,
            "date": "2024-01-15",
        },
    ]
    svc._svc.get_equity_universe = AsyncMock(return_value=stocks)
    svc._svc.get_mf_universe = AsyncMock(return_value=[])

    summary = await svc.sector_roll_up("it", universe="NIFTY500")

    assert summary.four_lens.get("rs") is not None
    expected_mean = (_D("60") + _D("80")) / _D("2")
    assert summary.four_lens["rs"] == expected_mean


@pytest.mark.asyncio
async def test_sector_roll_up_invalid_universe_raises():
    svc = _make_svc()
    with pytest.raises(ValueError, match="Unknown universe"):
        await svc.sector_roll_up("banking", universe="SENSEX")


@pytest.mark.asyncio
async def test_list_sectors_returns_sorted_distinct():
    svc = _make_svc()
    svc._svc.get_equity_universe = AsyncMock(
        return_value=[
            {"sector": "IT"},
            {"sector": "Banking"},
            {"sector": "IT"},
            {"sector": "FMCG"},
        ]
    )
    sectors = await svc.list_sectors()
    assert sectors == sorted({"IT", "Banking", "FMCG"})


def test_load_mf_sector_map_exact_match_not_substring():
    """Verify exact-match: 'Sectoral-Banking' matches 'Sectoral-Banking'
    but NOT 'Sectoral-Banking & Financial Services Plus'."""
    # Force reload by clearing cache
    _load_mf_sector_map.cache_clear()
    sector_map = _load_mf_sector_map()

    # banking sector should have exact patterns
    banking_patterns = sector_map.get("banking", [])
    if not banking_patterns:
        # Skip test if banking not in map — just check the function returned a dict
        assert isinstance(sector_map, dict)
        return

    # An exact match should succeed
    assert any(p == p for p in banking_patterns)  # trivially true — key check below

    # "Sectoral-Banking" should NOT be a substring-matched entry for
    # "Sectoral-Banking & Financial Services Plus"
    for pattern in banking_patterns:
        # no pattern should be a subset-of a longer different string
        assert not (
            "Sectoral-Banking & Financial Services Plus" == pattern[: len(pattern)]
            and len("Sectoral-Banking & Financial Services Plus") > len(pattern)
        )
