"""Tests for MF V2-7 routes: overlap, holding-stock, nav-history.

Uses mock JIPDataService to avoid real DB. Verifies:
- GET /overlap?funds=A,B → OverlapResponse (exact overlap_pct, Decimal fields)
- GET /overlap validation: <2 or >2 funds → 400
- GET /holding-stock/{symbol} → HoldingStockResponse (sorted by weight_pct desc)
- GET /{mstar_id}/nav-history → NAVHistoryResponse (points + coverage_gap_days)
- NAV history with gaps → correct coverage_gap_days
- NAV history empty → coverage_gap_days=0
- All tests use Decimal values, never float
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_freshness(nav_as_of: datetime.date | None = None) -> dict[str, Any]:
    return {
        "nav_as_of": nav_as_of or datetime.date(2026, 4, 10),
        "derived_as_of": datetime.date(2026, 4, 10),
        "holdings_as_of": datetime.date(2026, 3, 31),
        "sectors_as_of": datetime.date(2026, 3, 31),
        "flows_as_of": datetime.date(2026, 3, 1),
        "weighted_as_of": datetime.date(2026, 4, 10),
        "active_fund_count": 5,
    }


def _make_overlap_data(
    fund_a: str = "FUND_A",
    fund_b: str = "FUND_B",
    overlap_pct: Decimal = Decimal("35.50"),
    common_count: int = 5,
    count_a: int = 20,
    count_b: int = 18,
) -> dict[str, Any]:
    """Build overlap dict mirroring JIPMFService.get_fund_overlap output."""
    common_holdings = [
        {
            "instrument_id": f"INST{i:03d}",
            "holding_name": f"Stock {i}",
            "weight_pct_a": Decimal(f"{5 + i}.00"),
            "weight_pct_b": Decimal(f"{4 + i}.50"),
        }
        for i in range(1, common_count + 1)
    ]
    return {
        "mstar_id_a": fund_a,
        "mstar_id_b": fund_b,
        "overlap_pct": overlap_pct,
        "common_count": common_count,
        "count_a": count_a,
        "count_b": count_b,
        "common_holdings": common_holdings,
    }


def _make_holder_rows(n: int = 3) -> list[dict[str, Any]]:
    """Build fund holder rows mirroring JIPMFService.get_mf_holders output."""
    return [
        {
            "mstar_id": f"MSTAR{i:03d}",
            "fund_name": f"Fund {i}",
            "weight_pct": Decimal(f"{10 + i * 5}.00"),
            "shares_held": Decimal(f"{1000 * i}"),
            "market_value": Decimal(f"{500000 * i}.00"),
        }
        for i in range(1, n + 1)
    ]


def _make_nav_rows(
    dates: list[datetime.date],
    start_nav: Decimal = Decimal("100.00"),
) -> list[dict[str, Any]]:
    """Build NAV rows for given dates with incrementing NAV values."""
    return [
        {
            "nav_date": d,
            "nav": start_nav + Decimal(str(i)),
        }
        for i, d in enumerate(dates)
    ]


def _patch_svc_overlap(
    overlap_data: dict[str, Any],
    freshness: dict[str, Any] | None = None,
) -> MagicMock:
    mock_svc = MagicMock()
    mock_svc.get_fund_overlap = AsyncMock(return_value=overlap_data)
    mock_svc.get_mf_data_freshness = AsyncMock(return_value=freshness or _make_freshness())
    return mock_svc


def _patch_svc_holding_stock(
    holder_rows: list[dict[str, Any]],
    freshness: dict[str, Any] | None = None,
) -> MagicMock:
    mock_svc = MagicMock()
    mock_svc.get_mf_holders = AsyncMock(return_value=holder_rows)
    mock_svc.get_mf_data_freshness = AsyncMock(return_value=freshness or _make_freshness())
    return mock_svc


def _patch_svc_nav_history(
    nav_rows: list[dict[str, Any]],
    freshness: dict[str, Any] | None = None,
) -> MagicMock:
    mock_svc = MagicMock()
    mock_svc.get_fund_nav_history = AsyncMock(return_value=nav_rows)
    mock_svc.get_mf_data_freshness = AsyncMock(return_value=freshness or _make_freshness())
    return mock_svc


# ---------------------------------------------------------------------------
# TestOverlapRoute
# ---------------------------------------------------------------------------


class TestOverlapRoute:
    """Tests for GET /api/v1/mf/overlap."""

    def test_overlap_returns_200_two_funds(self) -> None:
        """Two valid fund IDs → HTTP 200."""
        overlap_data = _make_overlap_data()
        mock_svc = _patch_svc_overlap(overlap_data)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=FUND_A,FUND_B")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_overlap_returns_400_with_one_fund(self) -> None:
        """Only 1 fund ID → HTTP 400."""
        mock_svc = MagicMock()

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=FUND_A")

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_overlap_returns_400_with_three_funds(self) -> None:
        """Three fund IDs → HTTP 400."""
        mock_svc = MagicMock()

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=A,B,C")

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_overlap_response_structure(self) -> None:
        """Response must include fund_a, fund_b, overlap_pct, common_holdings, etc."""
        overlap_data = _make_overlap_data(
            fund_a="F001", fund_b="F002", overlap_pct=Decimal("42.75")
        )
        mock_svc = _patch_svc_overlap(overlap_data)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=F001,F002")

        body = resp.json()
        assert body["fund_a"] == "F001"
        assert body["fund_b"] == "F002"
        assert "overlap_pct" in body
        assert "common_holdings" in body
        assert "data_as_of" in body
        assert "staleness" in body

    def test_overlap_pct_is_decimal_string(self) -> None:
        """overlap_pct must be a Decimal string, not float."""
        overlap_data = _make_overlap_data(overlap_pct=Decimal("35.50"))
        mock_svc = _patch_svc_overlap(overlap_data)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=FUND_A,FUND_B")

        body = resp.json()
        assert isinstance(body["overlap_pct"], str), (
            f"overlap_pct must be Decimal string, got {type(body['overlap_pct'])}"
        )
        assert Decimal(body["overlap_pct"]) == Decimal("35.50")

    def test_overlap_common_holdings_mapped_correctly(self) -> None:
        """Common holdings must map instrument_id, symbol (holding_name), weight_a, weight_b."""
        overlap_data = _make_overlap_data(common_count=2)
        mock_svc = _patch_svc_overlap(overlap_data)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=FUND_A,FUND_B")

        body = resp.json()
        holdings = body["common_holdings"]
        assert len(holdings) == 2

        h = holdings[0]
        assert "instrument_id" in h
        assert "symbol" in h
        assert "weight_a" in h
        assert "weight_b" in h
        # Weights must be Decimal strings
        assert isinstance(h["weight_a"], str), f"weight_a must be Decimal string: {h['weight_a']}"
        assert isinstance(h["weight_b"], str), f"weight_b must be Decimal string: {h['weight_b']}"

    def test_overlap_symbol_is_holding_name(self) -> None:
        """OverlapHolding.symbol must map from holding_name field."""
        overlap_data = _make_overlap_data(common_count=1)
        mock_svc = _patch_svc_overlap(overlap_data)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=FUND_A,FUND_B")

        body = resp.json()
        holding = body["common_holdings"][0]
        # holding_name in fixture is "Stock 1"
        assert holding["symbol"] == "Stock 1"

    def test_overlap_empty_common_holdings_valid(self) -> None:
        """Zero common holdings → valid response, empty list."""
        overlap_data = {
            "mstar_id_a": "F001",
            "mstar_id_b": "F002",
            "overlap_pct": Decimal("0"),
            "common_count": 0,
            "count_a": 20,
            "count_b": 18,
            "common_holdings": [],
        }
        mock_svc = _patch_svc_overlap(overlap_data)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=F001,F002")

        assert resp.status_code == 200
        body = resp.json()
        assert body["common_holdings"] == []
        assert Decimal(body["overlap_pct"]) == Decimal("0")

    def test_overlap_3fund_fixture_exact(self) -> None:
        """3-fund fixture: overlap computation exact on known values.

        Simulate 3 overlap scenarios and verify overlap_pct passes through exactly.
        """
        test_cases = [
            ("FA", "FB", Decimal("25.00")),
            ("FC", "FD", Decimal("0.00")),
            ("FE", "FF", Decimal("100.00")),
        ]
        for fund_a, fund_b, expected_pct in test_cases:
            overlap_data = _make_overlap_data(
                fund_a=fund_a, fund_b=fund_b, overlap_pct=expected_pct, common_count=0
            )
            overlap_data["common_holdings"] = []
            mock_svc = _patch_svc_overlap(overlap_data)

            with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
                with patch("backend.routes.mf.get_db"):
                    client = TestClient(app)
                    resp = client.get(f"/api/v1/mf/overlap?funds={fund_a},{fund_b}")

            assert resp.status_code == 200
            body = resp.json()
            assert Decimal(body["overlap_pct"]) == expected_pct, (
                f"overlap_pct mismatch: expected {expected_pct}, got {body['overlap_pct']}"
            )


# ---------------------------------------------------------------------------
# TestHoldingStockRoute
# ---------------------------------------------------------------------------


class TestHoldingStockRoute:
    """Tests for GET /api/v1/mf/holding-stock/{symbol}."""

    def test_holding_stock_returns_200(self) -> None:
        """Symbol with holders → HTTP 200."""
        holder_rows = _make_holder_rows(3)
        mock_svc = _patch_svc_holding_stock(holder_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/holding-stock/RELIANCE")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_holding_stock_symbol_uppercased(self) -> None:
        """Symbol in response must be uppercased."""
        holder_rows = _make_holder_rows(2)
        mock_svc = _patch_svc_holding_stock(holder_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/holding-stock/reliance")

        body = resp.json()
        assert body["symbol"] == "RELIANCE"

    def test_holding_stock_sorted_by_weight_desc(self) -> None:
        """PUNCH LIST: funds sorted by weight_pct descending."""
        # Create rows with unordered weights
        holder_rows = [
            {
                "mstar_id": "A",
                "fund_name": "Fund A",
                "weight_pct": Decimal("5.00"),
                "shares_held": Decimal("100"),
                "market_value": Decimal("5000"),
            },
            {
                "mstar_id": "B",
                "fund_name": "Fund B",
                "weight_pct": Decimal("15.00"),
                "shares_held": Decimal("200"),
                "market_value": Decimal("15000"),
            },
            {
                "mstar_id": "C",
                "fund_name": "Fund C",
                "weight_pct": Decimal("10.00"),
                "shares_held": Decimal("150"),
                "market_value": Decimal("10000"),
            },
        ]
        mock_svc = _patch_svc_holding_stock(holder_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/holding-stock/INFY")

        body = resp.json()
        funds = body["funds"]
        assert len(funds) == 3
        weights = [Decimal(f["weight_pct"]) for f in funds]
        assert weights == sorted(weights, reverse=True), (
            f"Funds not sorted by weight_pct desc: {weights}"
        )
        assert weights[0] == Decimal("15.00")
        assert weights[1] == Decimal("10.00")
        assert weights[2] == Decimal("5.00")

    def test_holding_stock_weight_pct_is_decimal_string(self) -> None:
        """weight_pct must be Decimal string, not float."""
        holder_rows = _make_holder_rows(2)
        mock_svc = _patch_svc_holding_stock(holder_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/holding-stock/RELIANCE")

        body = resp.json()
        for fund in body["funds"]:
            assert isinstance(fund["weight_pct"], str), (
                f"weight_pct must be Decimal string, got {type(fund['weight_pct'])}"
            )
            _ = Decimal(fund["weight_pct"])  # must parse

    def test_holding_stock_empty_returns_200(self) -> None:
        """No funds hold the stock → HTTP 200 with empty list."""
        mock_svc = _patch_svc_holding_stock([])

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/holding-stock/UNKNOWNSYM")

        assert resp.status_code == 200
        body = resp.json()
        assert body["funds"] == []
        assert body["symbol"] == "UNKNOWNSYM"

    def test_holding_stock_response_structure(self) -> None:
        """Response must include symbol, funds, data_as_of, staleness."""
        holder_rows = _make_holder_rows(1)
        mock_svc = _patch_svc_holding_stock(holder_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/holding-stock/TCS")

        body = resp.json()
        for key in ("symbol", "funds", "data_as_of", "staleness"):
            assert key in body, f"Missing key: {key}"

    def test_holding_stock_fund_fields(self) -> None:
        """Each fund entry must have mstar_id, fund_name, weight_pct."""
        holder_rows = _make_holder_rows(1)
        mock_svc = _patch_svc_holding_stock(holder_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/holding-stock/TCS")

        body = resp.json()
        fund = body["funds"][0]
        assert "mstar_id" in fund
        assert "fund_name" in fund
        assert "weight_pct" in fund


# ---------------------------------------------------------------------------
# TestNAVHistoryRoute
# ---------------------------------------------------------------------------


class TestNAVHistoryRoute:
    """Tests for GET /api/v1/mf/{mstar_id}/nav-history."""

    def test_nav_history_returns_200(self) -> None:
        """NAV rows present → HTTP 200."""
        dates = [datetime.date(2026, 4, d) for d in range(1, 6)]
        nav_rows = _make_nav_rows(dates)
        mock_svc = _patch_svc_nav_history(nav_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_nav_history_empty_returns_200(self) -> None:
        """No NAV rows → HTTP 200 with empty points, coverage_gap_days=0."""
        mock_svc = _patch_svc_nav_history([])

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        assert resp.status_code == 200
        body = resp.json()
        assert body["points"] == []
        assert body["coverage_gap_days"] == 0

    def test_nav_history_single_point_gap_is_zero(self) -> None:
        """Single NAV point → coverage_gap_days=0."""
        nav_rows = _make_nav_rows([datetime.date(2026, 4, 1)])
        mock_svc = _patch_svc_nav_history(nav_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        body = resp.json()
        assert body["coverage_gap_days"] == 0

    def test_nav_history_no_gaps_consecutive_days(self) -> None:
        """5 consecutive days → coverage_gap_days=0."""
        dates = [datetime.date(2026, 4, d) for d in range(1, 6)]
        nav_rows = _make_nav_rows(dates)
        mock_svc = _patch_svc_nav_history(nav_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        body = resp.json()
        # Apr 1 to Apr 5: 5 calendar days, 5 points → gap = 0
        assert body["coverage_gap_days"] == 0

    def test_nav_history_gap_detection(self) -> None:
        """PUNCH LIST: NAV data with gaps → correct coverage_gap_days.

        Apr 1, Apr 3, Apr 5 = 5 calendar days span, 3 points → gap = 2
        """
        dates = [
            datetime.date(2026, 4, 1),
            datetime.date(2026, 4, 3),
            datetime.date(2026, 4, 5),
        ]
        nav_rows = _make_nav_rows(dates)
        mock_svc = _patch_svc_nav_history(nav_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        body = resp.json()
        # (Apr 5 - Apr 1).days + 1 = 5 calendar days, 3 points → gap = 2
        assert body["coverage_gap_days"] == 2, (
            f"Expected coverage_gap_days=2, got {body['coverage_gap_days']}"
        )

    def test_nav_history_large_gap(self) -> None:
        """Large gap: Jan 1 and Feb 1 → 31 calendar days, 2 points → gap = 30."""
        dates = [
            datetime.date(2026, 1, 1),
            datetime.date(2026, 2, 1),
        ]
        nav_rows = _make_nav_rows(dates)
        mock_svc = _patch_svc_nav_history(nav_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        body = resp.json()
        # (Feb 1 - Jan 1).days + 1 = 32 calendar days, 2 points → gap = 30
        assert body["coverage_gap_days"] == 30, (
            f"Expected coverage_gap_days=30, got {body['coverage_gap_days']}"
        )

    def test_nav_history_nav_is_decimal_string(self) -> None:
        """nav field in each point must be Decimal string, not float."""
        dates = [datetime.date(2026, 4, d) for d in range(1, 4)]
        nav_rows = _make_nav_rows(dates, start_nav=Decimal("150.75"))
        mock_svc = _patch_svc_nav_history(nav_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        body = resp.json()
        for pt in body["points"]:
            assert isinstance(pt["nav"], str), (
                f"nav must be Decimal string, got {type(pt['nav'])}: {pt['nav']}"
            )
            _ = Decimal(pt["nav"])  # must parse

    def test_nav_history_response_structure(self) -> None:
        """Response must include mstar_id, points, coverage_gap_days, data_as_of, staleness."""
        dates = [datetime.date(2026, 4, 1), datetime.date(2026, 4, 2)]
        nav_rows = _make_nav_rows(dates)
        mock_svc = _patch_svc_nav_history(nav_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history?from=2026-04-01&to=2026-04-02")

        body = resp.json()
        for key in ("mstar_id", "points", "coverage_gap_days", "data_as_of", "staleness"):
            assert key in body, f"Missing key: {key}"
        assert body["mstar_id"] == "F001"

    def test_nav_history_date_params_passed_to_service(self) -> None:
        """from/to query params must be forwarded to get_fund_nav_history."""
        nav_rows = _make_nav_rows([datetime.date(2026, 4, 1)])
        mock_svc = _patch_svc_nav_history(nav_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                client.get("/api/v1/mf/F001/nav-history?from=2026-01-01&to=2026-04-01")

        # Verify the service was called with the correct date params
        mock_svc.get_fund_nav_history.assert_called_once_with(
            "F001", date_from="2026-01-01", date_to="2026-04-01"
        )

    def test_nav_history_staleness_from_freshness(self) -> None:
        """Staleness flag correctly computed from freshness nav_as_of."""
        nav_rows = _make_nav_rows([datetime.date(2026, 4, 1)])
        freshness_fresh = _make_freshness(nav_as_of=datetime.date.today())
        mock_svc = _patch_svc_nav_history(nav_rows, freshness=freshness_fresh)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        body = resp.json()
        assert body["staleness"]["flag"] == "FRESH"
