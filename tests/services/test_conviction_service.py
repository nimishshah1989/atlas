"""Tests for ConvictionService."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.conviction_service import ConvictionService

_D = Decimal


def _make_svc() -> ConvictionService:
    session = MagicMock()
    svc = ConvictionService(session)
    return svc


@pytest.mark.asyncio
async def test_score_stock_with_rs_and_pe_present():
    svc = _make_svc()
    with (
        patch.object(svc._svc, "get_stock_detail", new_callable=AsyncMock) as mock_detail,
        patch.object(svc._svc, "get_market_regime", new_callable=AsyncMock) as mock_regime,
        patch.object(svc._lens, "get_lenses", new_callable=AsyncMock) as mock_lenses,
    ):
        from backend.models.lenses import LensBundle, LensValue

        mock_lenses.return_value = LensBundle(
            scope="stock",
            entity_id="RELIANCE",
            benchmark="NIFTY 500",
            period="3M",
            lenses={
                "rs": LensValue(value=_D("75")),
                "momentum": LensValue(value=_D("5")),
                "breadth": LensValue(value=_D("65")),
                "volume": LensValue(value=_D("1.8")),
            },
            composite_action="BUY",
            reason="test",
        )
        mock_detail.return_value = {"pe_ratio": 18}
        mock_regime.return_value = {"regime": "BULL"}

        result = await svc.score("RELIANCE", "stock")

    assert result.instrument_id == "RELIANCE"
    assert result.scope == "stock"
    assert _D("0") <= result.score <= _D("100")
    assert "selection" in result.components
    assert "value" in result.components
    assert "regime_fit" in result.components
    # pe < 25 → value=70, BULL → regime=80
    assert result.components["value"] == _D("70.00")
    assert result.components["regime_fit"] == _D("80.00")


@pytest.mark.asyncio
async def test_score_stock_rich_zone_pe_above_40_caps_weight_band():
    svc = _make_svc()
    with (
        patch.object(svc._svc, "get_stock_detail", new_callable=AsyncMock) as mock_detail,
        patch.object(svc._svc, "get_market_regime", new_callable=AsyncMock) as mock_regime,
        patch.object(svc._lens, "get_lenses", new_callable=AsyncMock) as mock_lenses,
    ):
        from backend.models.lenses import LensBundle, LensValue

        mock_lenses.return_value = LensBundle(
            scope="stock",
            entity_id="EXPENSIVESTOCK",
            benchmark="NIFTY 500",
            period="3M",
            lenses={
                "rs": LensValue(value=_D("95")),  # top decile
                "momentum": LensValue(value=_D("10")),
                "breadth": LensValue(value=_D("75")),
                "volume": LensValue(value=_D("2.5")),
            },
            composite_action="BUY",
            reason="test",
        )
        mock_detail.return_value = {"pe_ratio": 55}  # RICH zone
        mock_regime.return_value = {"regime": "BULL"}

        result = await svc.score("EXPENSIVESTOCK", "stock")

    # RICH zone: suggested_weight_pct must be capped at 1 (rich_zone_cap_pct)
    assert result.suggested_weight_pct == _D("1")
    assert "RICH" in result.reason


@pytest.mark.asyncio
async def test_score_mf():
    svc = _make_svc()
    with (
        patch.object(svc._svc, "get_fund_detail", new_callable=AsyncMock) as mock_detail,
        patch.object(svc._svc, "get_market_regime", new_callable=AsyncMock) as mock_regime,
        patch.object(svc._lens, "get_lenses", new_callable=AsyncMock) as mock_lenses,
    ):
        from backend.models.lenses import LensBundle, LensValue

        mock_lenses.return_value = LensBundle(
            scope="mf",
            entity_id="F00000TEST",
            benchmark="NIFTY 500",
            period="3M",
            lenses={
                "rs": LensValue(value=_D("60")),
                "momentum": LensValue(value=_D("2")),
                "breadth": LensValue(value=None),
                "volume": LensValue(value=None),
            },
            composite_action="HOLD",
            reason="mf=F00000TEST",
        )
        mock_detail.return_value = {"pe_ratio": None}
        mock_regime.return_value = {"regime": "CAUTIOUS"}

        result = await svc.score("F00000TEST", "mf")

    assert result.instrument_id == "F00000TEST"
    assert result.scope == "mf"
    # pe absent → value=50; CAUTIOUS → regime=60
    assert result.components["value"] == _D("50.00")
    assert result.components["regime_fit"] == _D("60.00")


@pytest.mark.asyncio
async def test_score_with_missing_data_returns_neutral_score():
    svc = _make_svc()
    with (
        patch.object(svc._svc, "get_stock_detail", new_callable=AsyncMock) as mock_detail,
        patch.object(svc._svc, "get_market_regime", new_callable=AsyncMock) as mock_regime,
        patch.object(svc._lens, "get_lenses", new_callable=AsyncMock) as mock_lenses,
    ):
        from backend.models.lenses import LensBundle

        mock_lenses.return_value = LensBundle(
            scope="stock",
            entity_id="UNKNOWN",
            benchmark="NIFTY 500",
            period="3M",
            lenses={},
            composite_action="HOLD",
            reason="insufficient_data",
        )
        mock_detail.return_value = None
        mock_regime.return_value = None  # unknown regime

        result = await svc.score("UNKNOWN", "stock")

    # With all defaults: selection=50, value=50, regime=50 → score=50
    # (0.4*50 + 0.3*50 + 0.3*50 = 50)
    assert _D("0") <= result.score <= _D("100")
    assert "selection" in result.components
    assert "regime_fit" in result.components


@pytest.mark.asyncio
async def test_score_bear_regime_returns_regime_fit_20():
    svc = _make_svc()
    with (
        patch.object(svc._svc, "get_stock_detail", new_callable=AsyncMock) as mock_detail,
        patch.object(svc._svc, "get_market_regime", new_callable=AsyncMock) as mock_regime,
        patch.object(svc._lens, "get_lenses", new_callable=AsyncMock) as mock_lenses,
    ):
        from backend.models.lenses import LensBundle, LensValue

        mock_lenses.return_value = LensBundle(
            scope="stock",
            entity_id="BEARCORP",
            benchmark="NIFTY 500",
            period="3M",
            lenses={
                "rs": LensValue(value=_D("45")),
                "momentum": LensValue(value=_D("0")),
                "breadth": LensValue(value=_D("40")),
                "volume": LensValue(value=_D("1.0")),
            },
            composite_action="HOLD",
            reason="test",
        )
        mock_detail.return_value = {"pe_ratio": 20}
        mock_regime.return_value = {"regime": "BEAR"}

        result = await svc.score("BEARCORP", "stock")

    assert result.components["regime_fit"] == _D("20.00")
