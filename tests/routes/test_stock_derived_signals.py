"""Route-level tests for Gold RS + Piotroski derived signals in GET /api/v1/stocks/{symbol}.

Uses ASGI transport + dependency_overrides[get_db] per FastAPI Dependency Patch Gotcha pattern.
Services are mocked at the module level: backend.routes.stocks.compute_gold_rs etc.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app
from backend.models.schemas import (
    GoldRS,
    GoldRSSignal,
    Piotroski,
    PiotroskiDetail,
)


# ---------------------------------------------------------------------------
# Minimal valid stock_detail fixture (mirrors existing test_stock_conviction.py)
# ---------------------------------------------------------------------------

_STOCK_ID = uuid4()

_BASE_STOCK_DATA: dict[str, Any] = {
    "id": _STOCK_ID,
    "symbol": "RELIANCE",
    "company_name": "Reliance Industries Ltd",
    "sector": "Energy",
    "industry": "Refineries",
    "nifty_50": True,
    "nifty_200": True,
    "nifty_500": True,
    "isin": "INE002A01018",
    "listing_date": None,
    "cap_category": "large",
    "close": Decimal("2800.00"),
    "rs_composite": Decimal("1.8"),
    "rs_momentum": Decimal("0.5"),
    "rs_1w": Decimal("0.2"),
    "rs_1m": Decimal("0.5"),
    "rs_3m": Decimal("0.8"),
    "rs_6m": Decimal("1.1"),
    "rs_12m": Decimal("1.5"),
    "rsi_14": Decimal("62.0"),
    "adx_14": Decimal("28.0"),
    "macd_histogram": Decimal("10.0"),
    "above_200dma": True,
    "above_50dma": True,
    "mf_holder_count": 420,
    "delivery_vs_avg": None,
    "sharpe_1y": Decimal("1.5"),
    "relative_volume": None,
    "volatility_20d": None,
    "max_drawdown_1y": None,
    "mfi_14": None,
    "sma_50": None,
    "sma_200": None,
    "ema_20": None,
    "macd_line": None,
    "macd_signal": None,
    "sortino_1y": None,
    "calmar_ratio": None,
    "obv": None,
    "bollinger_upper": None,
    "bollinger_lower": None,
    "disparity_20": None,
    "stochastic_k": None,
    "stochastic_d": None,
    "rs_date": "2026-04-17",
    "tech_date": "2026-04-17",
    "beta_nifty": None,
}

_GOLD_RS_FIXTURE = GoldRS(
    signal=GoldRSSignal.AMPLIFIES_BULL,
    ratio_3m=Decimal("1.0910"),
    stock_return_3m=Decimal("0.2000"),
    gold_return_3m=Decimal("0.1000"),
    as_of=datetime.date(2026, 4, 14),
)

_PIOTROSKI_FIXTURE = Piotroski(
    score=7,
    grade="GOOD",
    detail=PiotroskiDetail(
        f1_net_profit_positive=True,
        f2_cfo_positive=True,
        f3_roe_improving=True,
        f4_quality_earnings=True,
        f5_leverage_falling=True,
        f6_liquidity_improving=True,
        f7_no_dilution=True,
        f8_margin_expanding=False,
        f9_asset_turnover_improving=False,
    ),
    as_of=datetime.date(2025, 3, 31),
)


def _mock_db_session() -> AsyncMock:
    """Minimal mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_deep_dive_includes_gold_rs_and_piotroski() -> None:
    """GET /api/v1/stocks/RELIANCE returns stock.gold_rs and stock.piotroski.

    Verifies:
    - gold_rs.signal is one of the valid enum values
    - piotroski.score is in [0, 9]
    - piotroski.grade is one of {WEAK, NEUTRAL, GOOD, STRONG}
    """
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    try:
        with (
            patch("backend.routes.stocks.JIPDataService") as MockJIP,
            patch("backend.routes.stocks.TVCacheService") as MockTVCache,
            patch("backend.routes.stocks.TVBridgeClient"),
            patch(
                "backend.routes.stocks.compute_gold_rs",
                new=AsyncMock(return_value=_GOLD_RS_FIXTURE),
            ),
            patch(
                "backend.routes.stocks.compute_piotroski",
                new=AsyncMock(return_value=_PIOTROSKI_FIXTURE),
            ),
            patch(
                "backend.routes.stocks.async_session_factory",
                return_value=MagicMock(
                    __aenter__=AsyncMock(return_value=session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_stock_detail.return_value = _BASE_STOCK_DATA
            MockJIP.return_value = mock_svc

            mock_cache_inst = AsyncMock()
            mock_cache_inst.get_or_fetch.return_value = MagicMock(tv_data=None)
            MockTVCache.return_value = mock_cache_inst

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/stocks/RELIANCE")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()

    # Verify gold_rs is present and well-formed
    gold_rs = body["stock"]["gold_rs"]
    assert gold_rs is not None, "gold_rs should not be None"
    valid_signals = {"AMPLIFIES_BULL", "NEUTRAL", "FRAGILE", "AMPLIFIES_BEAR"}
    assert gold_rs["signal"] in valid_signals, (
        f"gold_rs.signal must be one of {valid_signals}, got {gold_rs['signal']}"
    )

    # Verify piotroski is present and well-formed
    piotroski = body["stock"]["piotroski"]
    assert piotroski is not None, "piotroski should not be None"
    assert 0 <= piotroski["score"] <= 9, (
        f"piotroski.score must be in [0,9], got {piotroski['score']}"
    )
    valid_grades = {"WEAK", "NEUTRAL", "GOOD", "STRONG"}
    assert piotroski["grade"] in valid_grades, (
        f"piotroski.grade must be one of {valid_grades}, got {piotroski['grade']}"
    )


@pytest.mark.asyncio
async def test_stock_deep_dive_includes_four_factor() -> None:
    """GET /api/v1/stocks/RELIANCE includes four_factor + C-DER-1 fields intact.

    Verifies:
    - stock.four_factor.conviction_level is one of the 5 ConvictionLevel values
    - stock.four_factor.action_signal is one of the 5 ActionSignal values
    - stock.four_factor.urgency is one of the 3 UrgencyLevel values
    - stock.gold_rs is still present (non-regression for C-DER-1)
    - stock.piotroski is still present (non-regression for C-DER-1)
    """
    from backend.models.conviction import (
        ActionSignal,
        ConvictionLevel,
        FourFactorConviction,
        UrgencyLevel,
    )

    four_factor_fixture = FourFactorConviction(
        conviction_level=ConvictionLevel.HIGH_PLUS,
        action_signal=ActionSignal.BUY,
        urgency=UrgencyLevel.IMMEDIATE,
        factor_returns_rs=True,
        factor_momentum_rs=True,
        factor_sector_rs=True,
        factor_volume_rs=True,
        factors_aligned=4,
        rs_composite=Decimal("110.0"),
    )

    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    try:
        with (
            patch("backend.routes.stocks.JIPDataService") as MockJIP,
            patch("backend.routes.stocks.TVCacheService") as MockTVCache,
            patch("backend.routes.stocks.TVBridgeClient"),
            patch(
                "backend.routes.stocks.compute_gold_rs",
                new=AsyncMock(return_value=_GOLD_RS_FIXTURE),
            ),
            patch(
                "backend.routes.stocks.compute_piotroski",
                new=AsyncMock(return_value=_PIOTROSKI_FIXTURE),
            ),
            patch(
                "backend.routes.stocks.compute_four_factor",
                new=AsyncMock(return_value=four_factor_fixture),
            ),
            patch(
                "backend.routes.stocks.async_session_factory",
                return_value=MagicMock(
                    __aenter__=AsyncMock(return_value=session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_stock_detail.return_value = _BASE_STOCK_DATA
            mock_svc.get_market_regime = AsyncMock(return_value={"regime": "BULL"})
            MockJIP.return_value = mock_svc

            mock_cache_inst = AsyncMock()
            mock_cache_inst.get_or_fetch.return_value = MagicMock(tv_data=None)
            MockTVCache.return_value = mock_cache_inst

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/stocks/RELIANCE")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()

    # Verify four_factor is present and well-formed
    four_factor = body["stock"]["four_factor"]
    assert four_factor is not None, "four_factor should not be None"

    valid_convictions = {"HIGH+", "HIGH", "MEDIUM", "LOW", "AVOID"}
    assert four_factor["conviction_level"] in valid_convictions, (
        f"conviction_level must be in {valid_convictions}, got {four_factor['conviction_level']}"
    )

    valid_actions = {"BUY", "ACCUMULATE", "WATCH", "REDUCE", "EXIT"}
    assert four_factor["action_signal"] in valid_actions, (
        f"action_signal must be in {valid_actions}, got {four_factor['action_signal']}"
    )

    valid_urgencies = {"IMMEDIATE", "DEVELOPING", "PATIENT"}
    assert four_factor["urgency"] in valid_urgencies, (
        f"urgency must be in {valid_urgencies}, got {four_factor['urgency']}"
    )

    # Non-regression: C-DER-1 fields must still be present
    assert body["stock"]["gold_rs"] is not None, (
        "gold_rs must still be present (C-DER-1 non-regression)"
    )
    assert body["stock"]["piotroski"] is not None, (
        "piotroski must still be present (C-DER-1 non-regression)"
    )


@pytest.mark.asyncio
async def test_breadth_response_includes_regime_enrichment() -> None:
    """GET /api/v1/stocks/breadth returns regime with days_in_regime int and regime_history list.

    Also verifies pre-C-DER-3 keys (breadth, regime, meta) are still present (non-regression).
    """
    import datetime

    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    breadth_data = {
        "date": datetime.date(2026, 4, 17),
        "advance": 350,
        "decline": 120,
        "unchanged": 30,
        "total_stocks": 500,
        "ad_ratio": 2.9,
        "pct_above_200dma": 65.0,
        "pct_above_50dma": 58.0,
        "new_52w_highs": 40,
        "new_52w_lows": 5,
        "mcclellan_oscillator": 45.0,
        "mcclellan_summation": 200.0,
    }
    regime_data = {
        "date": datetime.date(2026, 4, 17),
        "regime": "BULL",
        "confidence": 0.82,
        "breadth_score": 0.75,
        "momentum_score": 0.68,
        "volume_score": 0.60,
        "global_score": 0.55,
        "fii_score": 0.50,
    }

    from backend.models.schemas import RegimeTransition

    mock_transition = RegimeTransition(
        regime="BEAR",
        started_date=datetime.date(2026, 1, 1),
        ended_date=datetime.date(2026, 2, 28),
        duration_days=59,
        breadth_pct_at_start=None,
    )

    try:
        with (
            patch("backend.routes.stocks.JIPDataService") as MockJIP,
            patch(
                "backend.routes.stocks.compute_regime_enrichment",
                new=AsyncMock(return_value=(42, [mock_transition])),
            ),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_market_breadth.return_value = breadth_data
            mock_svc.get_market_regime.return_value = regime_data
            MockJIP.return_value = mock_svc

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/stocks/breadth")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()

    # Pre-C-DER-3 keys still present (non-regression)
    assert "breadth" in body, "breadth key must still be present"
    assert "regime" in body, "regime key must still be present"
    assert "meta" in body, "meta key must still be present"

    breadth = body["breadth"]
    assert breadth["advance"] == 350
    assert float(breadth["pct_above_200dma"]) == pytest.approx(65.0)

    regime = body["regime"]
    assert regime["regime"] == "BULL"

    # C-DER-3: regime enrichment fields
    assert "days_in_regime" in regime, "regime must include days_in_regime (C-DER-3 enrichment)"
    assert "regime_history" in regime, "regime must include regime_history (C-DER-3 enrichment)"

    days = regime["days_in_regime"]
    assert isinstance(days, int), f"days_in_regime must be int, got {type(days)}"
    assert days == 42

    history = regime["regime_history"]
    assert isinstance(history, list), f"regime_history must be list, got {type(history)}"
    assert len(history) == 1

    transition = history[0]
    assert transition["regime"] == "BEAR"
    assert transition["duration_days"] == 59
    assert transition["started_date"] == "2026-01-01"
    assert transition["ended_date"] == "2026-02-28"


@pytest.mark.asyncio
async def test_stock_deep_dive_survives_signal_failure() -> None:
    """GET /api/v1/stocks/RELIANCE returns 200 even when compute_gold_rs raises.

    Verifies:
    - Response is 200 (not 500)
    - stock.gold_rs is None when compute_gold_rs raises an exception
    - stock.piotroski is still populated (piotroski did not fail)
    """
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    try:
        with (
            patch("backend.routes.stocks.JIPDataService") as MockJIP,
            patch("backend.routes.stocks.TVCacheService") as MockTVCache,
            patch("backend.routes.stocks.TVBridgeClient"),
            patch(
                "backend.routes.stocks.compute_gold_rs",
                new=AsyncMock(side_effect=Exception("gold rs database error")),
            ),
            patch(
                "backend.routes.stocks.compute_piotroski",
                new=AsyncMock(return_value=_PIOTROSKI_FIXTURE),
            ),
            patch(
                "backend.routes.stocks.async_session_factory",
                return_value=MagicMock(
                    __aenter__=AsyncMock(return_value=session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_stock_detail.return_value = _BASE_STOCK_DATA
            MockJIP.return_value = mock_svc

            mock_cache_inst = AsyncMock()
            mock_cache_inst.get_or_fetch.return_value = MagicMock(tv_data=None)
            MockTVCache.return_value = mock_cache_inst

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/stocks/RELIANCE")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, (
        "Deep-dive must return 200 even when Gold RS computation fails"
    )
    body = response.json()

    # gold_rs must be None — the exception was swallowed
    assert body["stock"]["gold_rs"] is None, "gold_rs should be None when compute_gold_rs raises"

    # piotroski must still be populated
    piotroski = body["stock"]["piotroski"]
    assert piotroski is not None, "piotroski should still be populated when only gold_rs fails"
    assert piotroski["score"] == 7
    assert piotroski["grade"] == "GOOD"
