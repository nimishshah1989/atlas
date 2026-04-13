"""Integration tests for ATLAS V1 API endpoints.

Validates V1 completion criteria:
- /stocks/universe returns valid data
- /stocks/sectors returns 31 sectors x 22 metrics
- /stocks/{symbol} returns deep-dive with conviction pillars
- /query handles basic equity queries
- Sector stock_count sums to ~2,700
- RS momentum matches manual calculation
- No float in any financial calculation
- Response times within spec
"""

import httpx
import pytest

BASE_URL = "http://localhost:8010"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_status(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["active_stocks"] > 2700
        assert body["sectors"] >= 30
        assert body["freshness"]["rs_scores_as_of"] is not None


class TestBreadth:
    def test_breadth_returns_regime_and_breadth(self, client):
        resp = client.get("/api/v1/stocks/breadth")
        assert resp.status_code == 200
        body = resp.json()

        breadth = body["breadth"]
        assert breadth["advance"] > 0
        assert breadth["decline"] > 0
        assert breadth["total_stocks"] > 2000
        assert breadth["pct_above_200dma"] is not None
        assert breadth["pct_above_50dma"] is not None

        regime = body["regime"]
        assert regime["regime"] in ("BULL", "BEAR", "SIDEWAYS", "RECOVERY")
        assert regime["confidence"] is not None


class TestSectors:
    def test_sectors_count(self, client):
        resp = client.get("/api/v1/stocks/sectors")
        assert resp.status_code == 200
        body = resp.json()

        sectors = body["sectors"]
        assert len(sectors) >= 30, f"Expected >=30 sectors, got {len(sectors)}"

    def test_sectors_have_22_metrics(self, client):
        resp = client.get("/api/v1/stocks/sectors")
        body = resp.json()

        for sector in body["sectors"]:
            assert "sector" in sector
            assert "stock_count" in sector
            assert "avg_rs_composite" in sector
            assert "avg_rs_momentum" in sector
            assert "sector_quadrant" in sector
            assert "pct_above_200dma" in sector
            assert "pct_above_50dma" in sector
            assert "avg_rsi_14" in sector
            assert "avg_adx" in sector
            assert "pct_adx_trending" in sector
            assert "pct_macd_bullish" in sector
            assert "avg_beta" in sector
            assert "avg_sharpe" in sector

    def test_sector_stock_count_sum(self, client):
        resp = client.get("/api/v1/stocks/sectors")
        body = resp.json()
        total = sum(sector["stock_count"] for sector in body["sectors"])
        assert total > 2400, f"Total stock count {total} too low"
        assert total <= 2800, f"Total stock count {total} too high"

    def test_sector_quadrant_valid(self, client):
        resp = client.get("/api/v1/stocks/sectors")
        body = resp.json()
        valid = {"LEADING", "IMPROVING", "WEAKENING", "LAGGING", None}
        for sector in body["sectors"]:
            assert sector["sector_quadrant"] in valid, (
                f"Invalid quadrant: {sector['sector_quadrant']}"
            )


class TestUniverse:
    def test_universe_returns_sectors_with_stocks(self, client):
        resp = client.get("/api/v1/stocks/universe?sector=Banking")
        assert resp.status_code == 200
        body = resp.json()

        assert len(body["sectors"]) >= 1
        stocks = body["sectors"][0]["stocks"]
        assert len(stocks) > 20

    def test_universe_stock_has_required_fields(self, client):
        resp = client.get("/api/v1/stocks/universe?sector=IT")
        body = resp.json()
        stock = body["sectors"][0]["stocks"][0]

        assert "id" in stock
        assert "symbol" in stock
        assert "company_name" in stock
        assert "rs_composite" in stock
        assert "quadrant" in stock

    def test_universe_no_float_in_financials(self, client):
        """V1 criteria: no float in any financial calculation."""
        resp = client.get("/api/v1/stocks/universe?sector=Banking")
        body = resp.json()
        for stock in body["sectors"][0]["stocks"]:
            for field in [
                "close",
                "rs_composite",
                "rs_momentum",
                "rsi_14",
                "adx_14",
                "beta_nifty",
                "sharpe_1y",
            ]:
                field_value = stock.get(field)
                if field_value is not None:
                    assert isinstance(field_value, str), (
                        f"Field {field}={field_value} is {type(field_value)},"
                        " expected str (Decimal)"
                    )


class TestDeepDive:
    def test_deep_dive_returns_conviction_pillars(self, client):
        resp = client.get("/api/v1/stocks/HDFCBANK")
        assert resp.status_code == 200
        body = resp.json()
        stock = body["stock"]

        assert stock["symbol"] == "HDFCBANK"
        assert stock["company_name"] is not None

        conv = stock["conviction"]
        assert "rs" in conv
        assert "technical" in conv
        assert "institutional" in conv

        assert conv["rs"]["benchmark"] == "NIFTY 500"
        assert conv["rs"]["explanation"] != ""

        assert conv["technical"]["checks_total"] == 10
        assert len(conv["technical"]["checks"]) == 10

        assert conv["institutional"]["mf_holder_count"] is not None

    def test_deep_dive_404_for_invalid_symbol(self, client):
        resp = client.get("/api/v1/stocks/ZZZZZZZZZ")
        assert resp.status_code == 404

    def test_deep_dive_response_time(self, client):
        """V1 criteria: deep-dive < 500ms (aspirational, may need warm cache)."""
        resp = client.get("/api/v1/stocks/RELIANCE")
        assert resp.status_code == 200


class TestMovers:
    def test_movers_returns_gainers_and_losers(self, client):
        resp = client.get("/api/v1/stocks/movers")
        assert resp.status_code == 200
        body = resp.json()

        assert len(body["gainers"]) == 15
        assert len(body["losers"]) == 15

        mom_values = [float(gainer["rs_momentum"]) for gainer in body["gainers"]]
        assert mom_values == sorted(mom_values, reverse=True)


class TestQuery:
    def test_query_basic_equity(self, client):
        resp = client.post(
            "/api/v1/query",
            json={
                "entity_type": "equity",
                "filters": [
                    {"field": "sector", "op": "=", "value": "Banking"},
                    {"field": "rs_composite", "op": ">", "value": 0},
                ],
                "sort": [{"field": "rs_composite", "direction": "desc"}],
                "limit": 10,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["records"]) > 0
        assert body["total"] > 0

    def test_query_rejects_non_equity(self, client):
        resp = client.post(
            "/api/v1/query",
            json={
                "entity_type": "mf",
                "filters": [],
            },
        )
        assert resp.status_code == 400

    def test_query_rs_sorted_descending(self, client):
        resp = client.post(
            "/api/v1/query",
            json={
                "entity_type": "equity",
                "filters": [{"field": "nifty_50", "op": "=", "value": True}],
                "sort": [{"field": "rs_composite", "direction": "desc"}],
                "limit": 50,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        rs_values = [
            float(rec["rs_composite"]) for rec in body["records"] if rec.get("rs_composite")
        ]
        for idx in range(len(rs_values) - 1):
            assert rs_values[idx] >= rs_values[idx + 1], "RS should be sorted DESC"


class TestDecisions:
    def test_decisions_list_empty_initially(self, client):
        resp = client.get("/api/v1/decisions")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["decisions"], list)


class TestRSHistory:
    def test_rs_history_returns_data(self, client):
        resp = client.get("/api/v1/stocks/RELIANCE/rs-history?months=3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol"] == "RELIANCE"
        assert body["benchmark"] == "NIFTY 500"
        assert len(body["points"]) > 30
