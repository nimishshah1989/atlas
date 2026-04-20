"""Tests for RegimeComposer (S2-0)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.regime_service import (
    RegimeComposer,
    _band_confidence,
    _global_band_from_heatmap,
)

_D = Decimal


def _make_composer() -> RegimeComposer:
    session = MagicMock()
    return RegimeComposer(session)


def test_band_confidence_at_50_returns_zero():
    assert _band_confidence(_D("50")) == _D("0")


def test_band_confidence_at_100_returns_one():
    assert _band_confidence(_D("100")) == _D("1")


def test_band_confidence_at_70_returns_0_4():
    assert _band_confidence(_D("70")) == _D("0.4")


def test_global_band_risk_on_when_mean_above_60():
    rows = [{"rs_composite": 70}, {"rs_composite": 75}, {"rs_composite": 65}]
    band = _global_band_from_heatmap(rows)
    assert band.label == "RISK_ON"


def test_global_band_risk_off_when_mean_below_40():
    rows = [{"rs_composite": 30}, {"rs_composite": 35}, {"rs_composite": 25}]
    band = _global_band_from_heatmap(rows)
    assert band.label == "RISK_OFF"


def test_global_band_neutral_for_mid_range():
    rows = [{"rs_composite": 50}, {"rs_composite": 55}, {"rs_composite": 45}]
    band = _global_band_from_heatmap(rows)
    assert band.label == "NEUTRAL"


def test_global_band_unknown_when_no_rs_values():
    band = _global_band_from_heatmap([])
    assert band.label == "UNKNOWN"
    assert band.score == _D("50")


@pytest.mark.asyncio
async def test_compose_returns_composite_regime_with_posture():
    composer = _make_composer()
    with (
        patch.object(composer._svc, "get_global_rs_heatmap", new_callable=AsyncMock) as mock_g,
        patch.object(composer._svc, "get_market_breadth", new_callable=AsyncMock) as mock_b,
        patch.object(composer._svc, "get_sector_rollups", new_callable=AsyncMock) as mock_s,
    ):
        mock_g.return_value = [{"rs_composite": 70}, {"rs_composite": 75}]
        mock_b.return_value = {"breadth_score": 70, "drawdown_pct": 3, "date": "2026-04-20"}
        mock_s.return_value = [{"sector": "banking", "pct_above_200dma": 65}]

        composite = await composer.compose()

        assert composite.posture in {"RISK_ON", "SELECTIVE", "RISK_OFF"}
        assert composite.global_band.label == "RISK_ON"
        assert composite.india_band.score == _D("70.00")
        assert len(composite.sectors) == 1
        assert composite.sectors[0]["breadth_state"] == "GREEN"


@pytest.mark.asyncio
async def test_compose_degrades_gracefully_on_fetch_errors():
    composer = _make_composer()
    with (
        patch.object(composer._svc, "get_global_rs_heatmap", new_callable=AsyncMock) as mock_g,
        patch.object(composer._svc, "get_market_breadth", new_callable=AsyncMock) as mock_b,
        patch.object(composer._svc, "get_sector_rollups", new_callable=AsyncMock) as mock_s,
    ):
        mock_g.side_effect = RuntimeError("global fetch boom")
        mock_b.side_effect = RuntimeError("breadth fetch boom")
        mock_s.side_effect = RuntimeError("sectors fetch boom")

        composite = await composer.compose()

        assert composite.global_band.label == "UNKNOWN"
        assert composite.sectors == []
        assert composite.posture == "SELECTIVE"


def test_derive_posture_risk_on_requires_global_risk_on_and_india_bull():
    from backend.models.regime_v2 import RegimeBand

    g = RegimeBand(label="RISK_ON", score=_D("70"), confidence=_D("0.4"))
    i = RegimeBand(label="BULL", score=_D("70"), confidence=_D("0.4"))
    assert RegimeComposer._derive_posture(g, i) == "RISK_ON"


def test_derive_posture_risk_off_when_india_bear():
    from backend.models.regime_v2 import RegimeBand

    g = RegimeBand(label="RISK_ON", score=_D("70"), confidence=_D("0.4"))
    i = RegimeBand(label="BEAR", score=_D("20"), confidence=_D("0.6"))
    assert RegimeComposer._derive_posture(g, i) == "RISK_OFF"


def test_derive_posture_selective_default():
    from backend.models.regime_v2 import RegimeBand

    g = RegimeBand(label="NEUTRAL", score=_D("50"), confidence=_D("0"))
    i = RegimeBand(label="CAUTIOUS", score=_D("55"), confidence=_D("0.1"))
    assert RegimeComposer._derive_posture(g, i) == "SELECTIVE"
