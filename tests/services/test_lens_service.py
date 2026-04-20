"""Tests for LensService."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.lens_service import LensService

_D = Decimal


def _make_session() -> MagicMock:
    return MagicMock()


def _make_lens_service() -> LensService:
    session = _make_session()
    return LensService(session)


@pytest.mark.asyncio
async def test_lens_stock_returns_4_lenses():
    svc = _make_lens_service()
    with (
        patch.object(svc._svc, "get_stock_detail", new_callable=AsyncMock) as mock_detail,
        patch.object(svc._svc, "get_rs_history", new_callable=AsyncMock) as mock_history,
    ):
        mock_detail.return_value = {
            "rs_composite": 72,
            "rs_momentum": 5,
            "above_50dma": True,
            "above_200dma": True,
            "macd_histogram": 0.5,
            "rel_vol": 1.8,
            "date": "2024-01-15",
        }
        mock_history.return_value = [
            {"rs_composite": 71},
            {"rs_composite": 72},
            {"rs_composite": 73},
        ]
        bundle = await svc.get_lenses(scope="stock", entity_id="RELIANCE")

    assert bundle.scope == "stock"
    assert len(bundle.lenses) == 4
    assert set(bundle.lenses.keys()) == {"rs", "momentum", "breadth", "volume"}


@pytest.mark.asyncio
async def test_lens_sector_returns_4_lenses():
    svc = _make_lens_service()
    from backend.models.sectors import SectorSummary

    mock_summary = SectorSummary(
        key="banking",
        universe="NIFTY500",
        four_lens={
            "rs": _D("65"),
            "momentum": _D("3"),
            "breadth": _D("55"),
            "volume": _D("1.2"),
        },
        composite_action="HOLD",
        signals=[],
    )

    with patch(
        "backend.services.sector_service.SectorService.sector_roll_up",
        new_callable=AsyncMock,
        return_value=mock_summary,
    ):
        bundle = await svc.get_lenses(scope="sector", entity_id="banking")

    assert bundle.scope == "sector"
    assert len(bundle.lenses) == 4


@pytest.mark.asyncio
async def test_lens_mf_handles_missing_data():
    svc = _make_lens_service()
    with (
        patch.object(svc._svc, "get_fund_detail", new_callable=AsyncMock) as mock_detail,
        patch.object(svc._svc, "get_fund_weighted_technicals", new_callable=AsyncMock) as mock_tech,
    ):
        mock_detail.return_value = None
        mock_tech.return_value = None
        bundle = await svc.get_lenses(scope="mf", entity_id="F00000XXXX")

    # Should return empty bundle with HOLD action
    assert bundle.composite_action == "HOLD"
    assert bundle.reason == "insufficient_data"


@pytest.mark.asyncio
async def test_lens_country_handles_missing_data():
    svc = _make_lens_service()
    with patch.object(
        svc._svc, "get_global_rs_heatmap_all", new_callable=AsyncMock
    ) as mock_heatmap:
        mock_heatmap.return_value = []
        bundle = await svc.get_lenses(scope="country", entity_id="US")

    assert bundle.composite_action == "HOLD"
    assert bundle.reason == "insufficient_data"


@pytest.mark.asyncio
async def test_invalid_scope_raises_value_error():
    svc = _make_lens_service()
    with pytest.raises(ValueError, match="Unknown scope"):
        await svc.get_lenses(scope="invalid_scope", entity_id="TEST")


@pytest.mark.asyncio
async def test_invalid_period_raises_value_error():
    svc = _make_lens_service()
    with pytest.raises(ValueError, match="Unknown period"):
        await svc.get_lenses(scope="stock", entity_id="RELIANCE", period="7Y")
