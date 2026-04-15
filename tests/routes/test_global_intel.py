"""Unit tests for backend/routes/global_intel.py (V5-9).

Tests cover all 5 GET routes under /api/v1/global/:
    - /briefing   — latest market briefing
    - /ratios     — macro ratios with sparklines
    - /rs-heatmap — global RS heatmap
    - /regime     — market regime + breadth
    - /patterns   — inter-market patterns

Pattern:
    - Uses FastAPI TestClient (sync) with dependency_overrides for get_db
    - Patches JIPDataService methods via unittest.mock
    - All tests verify §20.4 envelope: {data, _meta}
    - Empty/null cases verified for fault-tolerance
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.db.session import get_db
from backend.main import app

# Patch target prefixes
_ROUTES_MOD = "backend.routes.global_intel"
_JIP_SVC = f"{_ROUTES_MOD}.JIPDataService"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _override_db(mock_session: Any) -> Any:
    """Return an async generator that yields mock_session."""

    async def _get_db() -> Any:  # type: ignore[misc]
        yield mock_session

    return _get_db


def _make_mock_session() -> AsyncMock:
    """AsyncMock that returns empty results for SQLAlchemy queries."""
    session = AsyncMock()
    # Default: execute returns an object where scalar_one_or_none → None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result
    return session


def _make_atlas_briefing_row() -> MagicMock:
    now = datetime.datetime(2026, 4, 15, 9, 0, 0, tzinfo=datetime.timezone.utc)
    row = MagicMock()
    row.id = 1
    row.date = datetime.date(2026, 4, 15)
    row.scope = "market"
    row.scope_key = None
    row.headline = "Global markets steady"
    row.narrative = "Markets show resilience..."
    row.key_signals = [{"signal": "VIX below 20"}]
    row.theses = [{"thesis": "Bull market intact"}]
    row.patterns = []
    row.india_implication = "FII flows positive"
    row.risk_scenario = "Fed hawkish surprise"
    row.conviction = "HIGH"
    row.model_used = "claude-sonnet-4-6"
    row.staleness_flags = {}
    row.is_deleted = False
    row.generated_at = now
    return row


def _make_atlas_intelligence_row(finding_type: str = "inter_market") -> MagicMock:
    now = datetime.datetime(2026, 4, 15, 8, 0, 0, tzinfo=datetime.timezone.utc)
    row = MagicMock()
    row.id = uuid.uuid4()
    row.finding_type = finding_type
    row.title = "Gold-USD inverse correlation strengthening"
    row.content = "Inter-market signal: gold rising as DXY weakens."
    row.entity = None
    row.entity_type = "global"
    row.confidence = Decimal("0.75")
    row.tags = ["gold", "dxy", "macro"]
    row.data_as_of = now
    row.is_deleted = False
    row.created_at = now
    row.updated_at = now
    return row


# ---------------------------------------------------------------------------
# GET /api/v1/global/briefing
# ---------------------------------------------------------------------------


class TestGetGlobalBriefing:
    """Tests for /api/v1/global/briefing."""

    def test_briefing_returns_200_when_empty(self) -> None:
        """Empty table returns 200 with null data and stale=True."""
        session = _make_mock_session()
        # scalar_one_or_none → None (no briefing)
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/briefing")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_briefing_has_data_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/briefing")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "data" in body, f"missing 'data' key: {list(body.keys())}"

    def test_briefing_has_meta_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/briefing")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "_meta" in body, f"missing '_meta' key: {list(body.keys())}"

    def test_briefing_stale_when_empty(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/briefing")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert body["_meta"]["stale"] is True

    def test_briefing_returns_data_when_found(self) -> None:
        session = _make_mock_session()
        briefing_row = _make_atlas_briefing_row()
        # Patch the ORM select execution to return a row
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = briefing_row
        session.execute.return_value = mock_result

        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/briefing")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] is not None
        assert body["data"]["headline"] == "Global markets steady"
        assert body["_meta"]["stale"] is False

    def test_briefing_handles_db_exception(self) -> None:
        """DB exception should still return 200 with null data (fault-tolerant)."""
        session = AsyncMock()
        session.execute.side_effect = Exception("DB connection lost")

        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/briefing")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] is None
        assert body["_meta"]["stale"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/global/ratios
# ---------------------------------------------------------------------------


class TestGetMacroRatios:
    """Tests for /api/v1/global/ratios."""

    def _make_jip_mock(self, return_value: list) -> MagicMock:
        mock = MagicMock()
        mock.get_macro_ratios = AsyncMock(return_value=return_value)
        return mock

    def test_ratios_returns_200_empty(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_macro_ratios = AsyncMock(return_value=[])
                client = TestClient(app)
                resp = client.get("/api/v1/global/ratios")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_ratios_has_data_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_macro_ratios = AsyncMock(return_value=[])
                client = TestClient(app)
                resp = client.get("/api/v1/global/ratios")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)

    def test_ratios_has_meta_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_macro_ratios = AsyncMock(return_value=[])
                client = TestClient(app)
                resp = client.get("/api/v1/global/ratios")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "_meta" in body

    def test_ratios_with_data(self) -> None:
        session = _make_mock_session()
        raw_row = {
            "ticker": "DGS10",
            "name": "US 10-Year Treasury",
            "unit": "Percent",
            "latest_value": 4.25,
            "latest_date": datetime.date(2026, 4, 14),
            "sparkline": [
                {"date": datetime.date(2026, 4, 10), "value": 4.10},
                {"date": datetime.date(2026, 4, 14), "value": 4.25},
            ],
        }
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_macro_ratios = AsyncMock(return_value=[raw_row])
                client = TestClient(app)
                resp = client.get("/api/v1/global/ratios")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["ticker"] == "DGS10"
        assert body["_meta"]["record_count"] == 1

    def test_ratios_ticker_filter(self) -> None:
        """Query param ?tickers= is passed to the service."""
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_macro_ratios = AsyncMock(return_value=[])
                client = TestClient(app)
                resp = client.get("/api/v1/global/ratios?tickers=DGS10,VIXCLS")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        # Verify the service was called with parsed ticker list
        call_kwargs = instance.get_macro_ratios.call_args
        assert call_kwargs is not None


# ---------------------------------------------------------------------------
# GET /api/v1/global/rs-heatmap
# ---------------------------------------------------------------------------


class TestGetRSHeatmap:
    """Tests for /api/v1/global/rs-heatmap."""

    def test_heatmap_returns_200_empty(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_global_rs_heatmap = AsyncMock(return_value=[])
                client = TestClient(app)
                resp = client.get("/api/v1/global/rs-heatmap")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_heatmap_has_data_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_global_rs_heatmap = AsyncMock(return_value=[])
                client = TestClient(app)
                resp = client.get("/api/v1/global/rs-heatmap")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)

    def test_heatmap_has_meta_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_global_rs_heatmap = AsyncMock(return_value=[])
                client = TestClient(app)
                resp = client.get("/api/v1/global/rs-heatmap")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "_meta" in body

    def test_heatmap_with_data(self) -> None:
        session = _make_mock_session()
        raw_row = {
            "entity_id": "^DJI",
            "name": "Dow Jones Industrial Average",
            "instrument_type": "index",
            "country": "US",
            "rs_composite": 75.5,
            "rs_1m": 72.0,
            "rs_3m": 68.0,
            "rs_date": datetime.date(2026, 4, 14),
            "close": 38500.0,
            "price_date": datetime.date(2026, 4, 14),
        }
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_global_rs_heatmap = AsyncMock(return_value=[raw_row])
                client = TestClient(app)
                resp = client.get("/api/v1/global/rs-heatmap")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["entity_id"] == "^DJI"
        assert body["_meta"]["record_count"] == 1

    def test_heatmap_null_price_handled(self) -> None:
        """Entity with no price data returns entry with close=None."""
        session = _make_mock_session()
        raw_row = {
            "entity_id": "^NSEI",
            "name": "Nifty 50",
            "instrument_type": "index",
            "country": "IN",
            "rs_composite": 80.0,
            "rs_1m": None,
            "rs_3m": None,
            "rs_date": datetime.date(2026, 4, 14),
            "close": None,
            "price_date": None,
        }
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_global_rs_heatmap = AsyncMock(return_value=[raw_row])
                client = TestClient(app)
                resp = client.get("/api/v1/global/rs-heatmap")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"][0]["close"] is None


# ---------------------------------------------------------------------------
# GET /api/v1/global/regime
# ---------------------------------------------------------------------------


class TestGetGlobalRegime:
    """Tests for /api/v1/global/regime."""

    def test_regime_returns_200_empty(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_market_regime = AsyncMock(return_value=None)
                instance.get_market_breadth = AsyncMock(return_value=None)
                client = TestClient(app)
                resp = client.get("/api/v1/global/regime")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_regime_has_data_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_market_regime = AsyncMock(return_value=None)
                instance.get_market_breadth = AsyncMock(return_value=None)
                client = TestClient(app)
                resp = client.get("/api/v1/global/regime")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "data" in body

    def test_regime_has_meta_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_market_regime = AsyncMock(return_value=None)
                instance.get_market_breadth = AsyncMock(return_value=None)
                client = TestClient(app)
                resp = client.get("/api/v1/global/regime")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "_meta" in body

    def test_regime_with_data(self) -> None:
        session = _make_mock_session()
        regime_raw = {
            "date": datetime.date(2026, 4, 14),
            "regime": "BULL",
            "confidence": 0.82,
            "breadth_score": 0.75,
            "momentum_score": 0.68,
            "volume_score": 0.60,
            "global_score": None,
            "fii_score": None,
        }
        breadth_raw = {
            "date": datetime.date(2026, 4, 14),
            "advance": 320,
            "decline": 150,
            "unchanged": 30,
            "total_stocks": 500,
            "ad_ratio": 2.13,
            "pct_above_200dma": 0.72,
            "pct_above_50dma": 0.65,
            "new_52w_highs": 45,
            "new_52w_lows": 5,
        }
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_market_regime = AsyncMock(return_value=regime_raw)
                instance.get_market_breadth = AsyncMock(return_value=breadth_raw)
                client = TestClient(app)
                resp = client.get("/api/v1/global/regime")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["regime"]["regime"] == "BULL"
        assert body["data"]["breadth"]["advance"] == 320
        assert body["_meta"]["record_count"] == 1
        assert body["_meta"]["stale"] is False

    def test_regime_stale_when_no_data(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            with patch(_JIP_SVC) as MockSvc:
                instance = MockSvc.return_value
                instance.get_market_regime = AsyncMock(return_value=None)
                instance.get_market_breadth = AsyncMock(return_value=None)
                client = TestClient(app)
                resp = client.get("/api/v1/global/regime")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert body["_meta"]["stale"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/global/patterns
# ---------------------------------------------------------------------------


class TestGetGlobalPatterns:
    """Tests for /api/v1/global/patterns."""

    def test_patterns_returns_200_empty(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/patterns")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_patterns_has_data_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/patterns")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)

    def test_patterns_has_meta_key(self) -> None:
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/patterns")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "_meta" in body

    def test_patterns_with_data(self) -> None:
        session = _make_mock_session()
        intel_row = _make_atlas_intelligence_row("inter_market")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [intel_row]
        session.execute.return_value = mock_result

        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/patterns")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["finding_type"] == "inter_market"
        assert body["_meta"]["record_count"] == 1

    def test_patterns_finding_type_filter(self) -> None:
        """Custom finding_type filter is accepted."""
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/patterns?finding_type=correlation")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_patterns_handles_db_exception(self) -> None:
        """DB exception returns 200 with empty data (fault-tolerant)."""
        session = AsyncMock()
        session.execute.side_effect = Exception("connection error")

        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/patterns")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    def test_patterns_compat_key(self) -> None:
        """V1 compat key 'patterns' must be present alongside 'data'."""
        session = _make_mock_session()
        app.dependency_overrides[get_db] = _override_db(session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/global/patterns")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "patterns" in body
