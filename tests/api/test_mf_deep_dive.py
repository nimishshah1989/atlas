"""Tests for MF deep-dive, holdings, and sectors routes (V2-5).

Uses mock JIPDataService to avoid real DB. Verifies:
- GET /{mstar_id} → FundDeepDiveResponse (identity, pillars, RS, staleness, inactive)
- GET /{mstar_id}/holdings → HoldingsResponse (coverage_pct, warnings, Decimal fields)
- GET /{mstar_id}/sectors → FundSectorsResponse (sectors, as_of_date, Decimal fields)
- PUNCH LIST: manager_alpha == derived_rs_composite - nav_rs_composite (exact Decimal, 50 funds)
- PUNCH LIST: holdings weights sum to ~100% ±1%
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_detail_row(
    mstar_id: str = "F001",
    derived_rs_composite: Any = Decimal("72.5"),
    nav_rs_composite: Any = Decimal("68.0"),
    manager_alpha: Any = Decimal("4.5"),
    is_active: bool = True,
    inception_date: Any = datetime.date(2010, 1, 1),
) -> dict[str, Any]:
    """Build a fund detail dict mirroring FUND_DETAIL_SQL output."""
    return {
        "mstar_id": mstar_id,
        "fund_name": f"Test Fund {mstar_id}",
        "amc_name": "Test AMC",
        "category_name": "Flexi Cap",
        "broad_category": "Equity",
        "is_index_fund": False,
        "is_etf": False,
        "is_active": is_active,
        "inception_date": inception_date,
        "closure_date": None,
        "merged_into_mstar_id": None,
        "primary_benchmark": "NIFTY 500 TRI",
        "expense_ratio": Decimal("1.25"),
        "investment_strategy": None,
        "nav": Decimal("150.00"),
        "nav_date": datetime.date(2026, 4, 10),
        "derived_date": datetime.date(2026, 4, 10),
        "derived_rs_composite": derived_rs_composite,
        "nav_rs_composite": nav_rs_composite,
        "manager_alpha": manager_alpha,
        "coverage_pct": Decimal("98.5"),
        "sharpe_1y": Decimal("0.9"),
        "sharpe_3y": Decimal("0.8"),
        "sharpe_5y": Decimal("0.7"),
        "sortino_1y": Decimal("1.2"),
        "sortino_3y": Decimal("1.0"),
        "sortino_5y": Decimal("0.9"),
        "max_drawdown_1y": Decimal("-0.12"),
        "max_drawdown_3y": Decimal("-0.18"),
        "max_drawdown_5y": Decimal("-0.22"),
        "volatility_1y": Decimal("0.15"),
        "volatility_3y": Decimal("0.14"),
        "stddev_1y": Decimal("0.15"),
        "stddev_3y": Decimal("0.14"),
        "stddev_5y": Decimal("0.13"),
        "beta_vs_nifty": Decimal("0.92"),
        "information_ratio": Decimal("0.45"),
        "treynor_ratio": Decimal("0.08"),
        "sector_count": 10,
        "sector_as_of": datetime.date(2026, 3, 31),
        "holding_count": 45,
        "holdings_as_of": datetime.date(2026, 3, 31),
        "weighted_as_of": datetime.date(2026, 4, 10),
        "weighted_rsi": Decimal("58.2"),
        "weighted_breadth_pct_above_200dma": Decimal("72.0"),
        "weighted_macd_bullish_pct": Decimal("60.5"),
    }


def _make_momentum_batch(mstar_id: str, rs_momentum_28d: Any = Decimal("5.0")) -> dict[str, Any]:
    return {
        mstar_id: {
            "mstar_id": mstar_id,
            "latest_date": datetime.date(2026, 4, 10),
            "latest_rs_composite": Decimal("72.5"),
            "past_date": datetime.date(2026, 3, 13),
            "past_rs_composite": Decimal("67.5"),
            "rs_momentum_28d": rs_momentum_28d,
        }
    }


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


def _make_lifecycle_events() -> list[dict[str, Any]]:
    return [
        {
            "mstar_id": "F001",
            "event_type": "MERGER",
            "effective_date": datetime.date(2023, 6, 1),
            "detail": "Merged with sibling fund",
        }
    ]


def _make_holding_rows(
    n: int = 5, total_weight: Decimal = Decimal("100.0")
) -> list[dict[str, Any]]:
    """Generate n holding rows whose weights sum to total_weight."""
    per_weight = total_weight / n
    rows = []
    for i in range(n):
        inst_id = str(uuid.UUID(int=i + 1))
        rows.append(
            {
                "mstar_id": "F001",
                "as_of_date": datetime.date(2026, 3, 31),
                "holding_name": f"Stock {i + 1}",
                "isin": f"INE00{i:03d}K01019",
                "instrument_id": inst_id,
                "weight_pct": per_weight,
                "shares_held": Decimal(f"{1000 * (i + 1)}"),
                "market_value": Decimal(f"{50000 * (i + 1)}.00"),
                "sector_code": "FINANCIALS",
                "is_mapped": True,
                "current_symbol": f"STK{i + 1:03d}",
                "sector": "Financials",
                "rs_composite": Decimal(f"{60 + i}.5"),
                "above_200dma": True,
                "rsi_14": Decimal("55.0"),
            }
        )
    return rows


def _make_sector_rows(n: int = 5) -> list[dict[str, Any]]:
    sectors = ["Financials", "IT", "Healthcare", "Energy", "Materials"]
    rows = []
    for i in range(n):
        rows.append(
            {
                "sector": sectors[i % len(sectors)],
                "weight_pct": Decimal(f"{20}.0"),
                "stock_count": 5,
                "as_of_date": datetime.date(2026, 3, 31),
                "sector_rs_composite": Decimal(f"{55 + i}.0"),
            }
        )
    return rows


def _patch_svc_deep_dive(
    detail: dict[str, Any] | None,
    lifecycle: list[dict[str, Any]] | None = None,
    freshness: dict[str, Any] | None = None,
    rs_batch: dict[str, Any] | None = None,
) -> MagicMock:
    mock_svc = MagicMock()
    mock_svc.get_fund_detail = AsyncMock(return_value=detail)
    mock_svc.get_fund_lifecycle = AsyncMock(return_value=lifecycle or [])
    mock_svc.get_mf_data_freshness = AsyncMock(return_value=freshness or _make_freshness())
    mock_svc.get_mf_rs_momentum_batch = AsyncMock(return_value=rs_batch or {})
    return mock_svc


def _patch_svc_holdings(holding_rows: list[dict[str, Any]]) -> MagicMock:
    mock_svc = MagicMock()
    mock_svc.get_fund_holdings = AsyncMock(return_value=holding_rows)
    return mock_svc


def _patch_svc_sectors(sector_rows: list[dict[str, Any]]) -> MagicMock:
    mock_svc = MagicMock()
    mock_svc.get_fund_sectors = AsyncMock(return_value=sector_rows)
    return mock_svc


# ---------------------------------------------------------------------------
# TestDeepDiveRoute
# ---------------------------------------------------------------------------


class TestDeepDiveRoute:
    """Tests for GET /api/v1/mf/{mstar_id}."""

    def test_deep_dive_returns_200(self) -> None:
        """Fund exists → HTTP 200."""
        detail = _make_detail_row()
        mock_svc = _patch_svc_deep_dive(detail, rs_batch=_make_momentum_batch("F001"))

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_deep_dive_404_on_missing_fund(self) -> None:
        """get_fund_detail returns None → HTTP 404."""
        mock_svc = _patch_svc_deep_dive(None)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/NONEXISTENT")

        assert resp.status_code == 404

    def test_deep_dive_identity_fields_correct(self) -> None:
        """Identity block must carry mstar_id, fund_name, category etc."""
        detail = _make_detail_row(mstar_id="F999")
        mock_svc = _patch_svc_deep_dive(detail, rs_batch=_make_momentum_batch("F999"))

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F999")

        body = resp.json()
        identity = body["identity"]
        assert identity["mstar_id"] == "F999"
        assert identity["fund_name"] == "Test Fund F999"
        assert identity["amc_name"] == "Test AMC"
        assert identity["category_name"] == "Flexi Cap"
        assert identity["broad_category"] == "Equity"
        assert identity["primary_benchmark"] == "NIFTY 500 TRI"
        assert identity["is_index_fund"] is False

    def test_deep_dive_manager_alpha_exact_decimal(self) -> None:
        """PUNCH LIST: 50 funds — manager_alpha == derived_rs_composite - nav_rs_composite.

        manager_alpha in the JIP detail row is already computed as
        derived_rs_composite - nav_rs_composite. The route passes it through
        unchanged. This test verifies the exact Decimal relationship for all 50.
        """
        import random

        rng = random.Random(42)  # deterministic seed

        for i in range(50):
            # Generate varied Decimal values
            derived_int = rng.randint(1, 99)
            derived_frac = rng.randint(0, 99)
            nav_int = rng.randint(1, 99)
            nav_frac = rng.randint(0, 99)

            derived_rs = Decimal(f"{derived_int}.{derived_frac:02d}")
            nav_rs = Decimal(f"{nav_int}.{nav_frac:02d}")
            # Store the EXACT computed alpha — as JIP's de_mf_derived_daily would
            expected_alpha = derived_rs - nav_rs

            detail = _make_detail_row(
                mstar_id=f"F{i:03d}",
                derived_rs_composite=derived_rs,
                nav_rs_composite=nav_rs,
                manager_alpha=expected_alpha,
            )
            rs_batch = _make_momentum_batch(f"F{i:03d}", rs_momentum_28d=Decimal("3.0"))
            mock_svc = _patch_svc_deep_dive(detail, rs_batch=rs_batch)

            with (
                patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
                patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
            ):
                with patch("backend.routes.mf.get_db"):
                    client = TestClient(app)
                    resp = client.get(f"/api/v1/mf/F{i:03d}")

            assert resp.status_code == 200, f"fund F{i:03d}: {resp.text}"
            body = resp.json()
            reported_alpha_str = body["pillars"]["performance"]["manager_alpha"]
            assert reported_alpha_str is not None, f"fund F{i:03d}: manager_alpha is null"
            reported_alpha = Decimal(reported_alpha_str)
            assert reported_alpha == expected_alpha, (
                f"fund F{i:03d}: manager_alpha {reported_alpha} != derived - nav = {expected_alpha}"
            )

    def test_deep_dive_no_float_in_response(self) -> None:
        """All financial fields in response must be str (Decimal-serialised), not float."""
        detail = _make_detail_row()
        mock_svc = _patch_svc_deep_dive(detail, rs_batch=_make_momentum_batch("F001"))

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        body = resp.json()

        def _assert_no_float_in(obj: Any, path: str = "") -> None:
            if isinstance(obj, float):
                raise AssertionError(f"Float found at {path}: {obj}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    _assert_no_float_in(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    _assert_no_float_in(item, f"{path}[{idx}]")

        _assert_no_float_in(body)

    def test_deep_dive_quadrant_set_from_rs(self) -> None:
        """rs_strength.quadrant must be correctly set from rs_composite and rs_momentum_28d."""
        # derived_rs > 0, momentum > 0 → LEADING
        detail = _make_detail_row(
            derived_rs_composite=Decimal("70.0"),
            nav_rs_composite=Decimal("65.0"),
            manager_alpha=Decimal("5.0"),
        )
        rs_batch = _make_momentum_batch("F001", rs_momentum_28d=Decimal("5.0"))
        mock_svc = _patch_svc_deep_dive(detail, rs_batch=rs_batch)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        body = resp.json()
        assert body["pillars"]["rs_strength"]["quadrant"] == "LEADING"

        # derived_rs > 0, momentum < 0 → WEAKENING
        rs_batch_weakening = _make_momentum_batch("F001", rs_momentum_28d=Decimal("-3.0"))
        mock_svc2 = _patch_svc_deep_dive(detail, rs_batch=rs_batch_weakening)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc2),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc2),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp2 = client.get("/api/v1/mf/F001")

        body2 = resp2.json()
        assert body2["pillars"]["rs_strength"]["quadrant"] == "WEAKENING"

    def test_deep_dive_staleness_correct(self) -> None:
        """Staleness flag must match freshness data."""
        detail = _make_detail_row()
        rs_batch = _make_momentum_batch("F001")

        # FRESH: today
        freshness_fresh = _make_freshness(nav_as_of=datetime.date.today())
        mock_svc = _patch_svc_deep_dive(detail, freshness=freshness_fresh, rs_batch=rs_batch)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        assert resp.json()["staleness"]["flag"] == "FRESH"

        # EXPIRED: 5 days ago
        stale_date = datetime.date.today() - datetime.timedelta(days=5)
        freshness_expired = _make_freshness(nav_as_of=stale_date)
        mock_svc2 = _patch_svc_deep_dive(detail, freshness=freshness_expired, rs_batch=rs_batch)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc2),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc2),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp2 = client.get("/api/v1/mf/F001")

        assert resp2.json()["staleness"]["flag"] == "EXPIRED"

    def test_deep_dive_inactive_flag(self) -> None:
        """is_active=False → inactive=True in response."""
        detail = _make_detail_row(is_active=False)
        mock_svc = _patch_svc_deep_dive(detail, rs_batch=_make_momentum_batch("F001"))

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        body = resp.json()
        assert body["inactive"] is True

    def test_deep_dive_active_fund_inactive_is_null(self) -> None:
        """is_active=True → inactive is null/None in response."""
        detail = _make_detail_row(is_active=True)
        mock_svc = _patch_svc_deep_dive(detail, rs_batch=_make_momentum_batch("F001"))

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        body = resp.json()
        assert body["inactive"] is None

    def test_deep_dive_lifecycle_event_populated(self) -> None:
        """First lifecycle event must appear in mf_lifecycle_event."""
        detail = _make_detail_row()
        lifecycle = _make_lifecycle_events()
        mock_svc = _patch_svc_deep_dive(
            detail, lifecycle=lifecycle, rs_batch=_make_momentum_batch("F001")
        )

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        body = resp.json()
        evt = body["mf_lifecycle_event"]
        assert evt is not None
        assert evt["event_type"] == "MERGER"
        assert evt["effective_date"] == "2023-06-01"
        assert evt["detail"] == "Merged with sibling fund"

    def test_deep_dive_no_lifecycle_event_when_empty(self) -> None:
        """No lifecycle events → mf_lifecycle_event is null."""
        detail = _make_detail_row()
        mock_svc = _patch_svc_deep_dive(detail, lifecycle=[], rs_batch=_make_momentum_batch("F001"))

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        assert resp.json()["mf_lifecycle_event"] is None

    def test_deep_dive_structure(self) -> None:
        """Response must include all required top-level fields."""
        detail = _make_detail_row()
        mock_svc = _patch_svc_deep_dive(detail, rs_batch=_make_momentum_batch("F001"))

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        body = resp.json()
        for key in (
            "identity",
            "daily",
            "pillars",
            "sector_exposure",
            "top_holdings",
            "weighted_technicals",
            "data_as_of",
            "staleness",
        ):
            assert key in body, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# TestHoldingsRoute
# ---------------------------------------------------------------------------


class TestHoldingsRoute:
    """Tests for GET /api/v1/mf/{mstar_id}/holdings."""

    def test_holdings_returns_200(self) -> None:
        holding_rows = _make_holding_rows(5)
        mock_svc = _patch_svc_holdings(holding_rows)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/holdings")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_holdings_weights_sum_near_100(self) -> None:
        """PUNCH LIST: fixture weights sum to ~100%, coverage_pct reflects this."""
        holding_rows = _make_holding_rows(10, total_weight=Decimal("100.0"))
        mock_svc = _patch_svc_holdings(holding_rows)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/holdings")

        body = resp.json()
        coverage = Decimal(body["coverage_pct"])
        # Weights were constructed to sum to 100.0 ±1%
        assert abs(coverage - Decimal("100")) <= Decimal("1"), (
            f"coverage_pct {coverage} not within 1% of 100"
        )
        # No warning expected when coverage is ~100%
        assert body["warnings"] == []

    def test_holdings_coverage_warning_when_low(self) -> None:
        """Holdings weights sum to < 99% → warning present."""
        holding_rows = _make_holding_rows(5, total_weight=Decimal("90.0"))
        mock_svc = _patch_svc_holdings(holding_rows)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/holdings")

        body = resp.json()
        assert len(body["warnings"]) > 0
        assert "coverage" in body["warnings"][0].lower()

    def test_holdings_empty_returns_200(self) -> None:
        """No holdings → empty list, HTTP 200."""
        mock_svc = _patch_svc_holdings([])

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/holdings")

        assert resp.status_code == 200
        body = resp.json()
        assert body["holdings"] == []
        assert body["coverage_pct"] == "0"

    def test_holdings_decimal_fields(self) -> None:
        """weight_pct, market_value, rs_composite must be Decimal strings."""
        holding_rows = _make_holding_rows(3)
        mock_svc = _patch_svc_holdings(holding_rows)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/holdings")

        body = resp.json()
        for h in body["holdings"]:
            for field in ("weight_pct", "market_value", "rs_composite"):
                val = h.get(field)
                if val is not None:
                    assert isinstance(val, str), (
                        f"Holding field '{field}' must be Decimal string, got {type(val)}: {val}"
                    )

    def test_holdings_coverage_warning_when_high(self) -> None:
        """Holdings weights sum to > 101% → warning present."""
        holding_rows = _make_holding_rows(5, total_weight=Decimal("105.0"))
        mock_svc = _patch_svc_holdings(holding_rows)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/holdings")

        body = resp.json()
        assert len(body["warnings"]) > 0


# ---------------------------------------------------------------------------
# TestSectorsRoute
# ---------------------------------------------------------------------------


class TestSectorsRoute:
    """Tests for GET /api/v1/mf/{mstar_id}/sectors."""

    def test_sectors_returns_200(self) -> None:
        sector_rows = _make_sector_rows(5)
        mock_svc = _patch_svc_sectors(sector_rows)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/sectors")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_sectors_structure(self) -> None:
        """Response must include sectors list and as_of_date."""
        sector_rows = _make_sector_rows(3)
        mock_svc = _patch_svc_sectors(sector_rows)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/sectors")

        body = resp.json()
        assert "sectors" in body
        assert "as_of_date" in body
        assert len(body["sectors"]) == 3
        # Check first sector fields
        sector = body["sectors"][0]
        assert "sector" in sector
        assert "weight_pct" in sector
        assert "stock_count" in sector

    def test_sectors_decimal_weight(self) -> None:
        """weight_pct must be Decimal string (not float)."""
        sector_rows = _make_sector_rows(4)
        mock_svc = _patch_svc_sectors(sector_rows)

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/sectors")

        body = resp.json()
        for s in body["sectors"]:
            val = s.get("weight_pct")
            assert val is not None
            assert isinstance(val, str), (
                f"weight_pct must be Decimal string, got {type(val)}: {val}"
            )
            # Must be parseable as Decimal
            _ = Decimal(val)

    def test_sectors_empty_returns_200(self) -> None:
        """Empty sectors → HTTP 200 with empty list."""
        mock_svc = _patch_svc_sectors([])

        with (
            patch("backend.routes.mf.JIPDataService", return_value=mock_svc),
            patch("backend.routes.mf_helpers.JIPDataService", return_value=mock_svc),
        ):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/sectors")

        assert resp.status_code == 200
        body = resp.json()
        assert body["sectors"] == []


class TestDeepDiveParallelization:
    """v2-09 cold-path fix: the four independent deep-dive queries run in
    parallel on separate sessions.

    Regression guard for the 5s cold latency. Before the fix, the handler
    awaited `get_fund_detail` → `get_fund_lifecycle` → `get_mf_data_freshness`
    → `rs_momentum_or_empty` sequentially on one session. A single asyncpg
    connection cannot multiplex concurrent queries, so a shared session
    serialized them. The fix calls each fetch inside its own session via
    `asyncio.gather`, so cold-path wall time is max(fetches) not sum(fetches).
    """

    def test_handler_dispatches_four_fetches_concurrently(self) -> None:
        """Injecting 200ms into each fetch: total must be ~200ms (gather),
        not ~800ms (sequential). Allow 300ms margin for TestClient overhead."""
        import asyncio as _asyncio
        import time

        call_log: list[tuple[str, float]] = []
        start_ref = [0.0]

        async def _sleepy_detail(mstar_id: str):
            call_log.append(("detail_enter", time.monotonic() - start_ref[0]))
            await _asyncio.sleep(0.2)
            call_log.append(("detail_exit", time.monotonic() - start_ref[0]))
            return _make_detail_row(mstar_id=mstar_id)

        async def _sleepy_lifecycle(mstar_id: str):
            call_log.append(("lifecycle_enter", time.monotonic() - start_ref[0]))
            await _asyncio.sleep(0.2)
            call_log.append(("lifecycle_exit", time.monotonic() - start_ref[0]))
            return []

        async def _sleepy_freshness():
            call_log.append(("freshness_enter", time.monotonic() - start_ref[0]))
            await _asyncio.sleep(0.2)
            call_log.append(("freshness_exit", time.monotonic() - start_ref[0]))
            return _make_freshness()

        async def _sleepy_rs():
            call_log.append(("rs_enter", time.monotonic() - start_ref[0]))
            await _asyncio.sleep(0.2)
            call_log.append(("rs_exit", time.monotonic() - start_ref[0]))
            return {}

        with (
            patch("backend.routes.mf.fetch_deep_dive_detail", _sleepy_detail),
            patch("backend.routes.mf.fetch_deep_dive_lifecycle", _sleepy_lifecycle),
            patch("backend.routes.mf.fetch_deep_dive_freshness", _sleepy_freshness),
            patch("backend.routes.mf.fetch_deep_dive_rs_batch", _sleepy_rs),
        ):
            client = TestClient(app)
            start_ref[0] = time.monotonic()
            resp = client.get("/api/v1/mf/F001")
            wall_ms = (time.monotonic() - start_ref[0]) * 1000

        assert resp.status_code == 200, resp.text
        # Four entered, four exited
        enters = [name for name, _ in call_log if name.endswith("_enter")]
        assert len(enters) == 4, f"Expected 4 fetches, got {len(enters)}: {call_log}"

        # All four must have ENTERED before any exit — proof of concurrency.
        # In sequential execution, detail_exit would happen before
        # lifecycle_enter.
        enter_times = {name: t for name, t in call_log if name.endswith("_enter")}
        exit_times = {name: t for name, t in call_log if name.endswith("_exit")}
        last_enter = max(enter_times.values())
        first_exit = min(exit_times.values())
        assert last_enter < first_exit, (
            f"Sequential dispatch detected — last enter at {last_enter:.3f}s "
            f"was after first exit at {first_exit:.3f}s. Log: {call_log}"
        )

        # Wall time ceiling: with 4 × 200ms concurrent, must be < 500ms.
        assert wall_ms < 500, f"Parallel wall time {wall_ms:.0f}ms exceeds 500ms budget"
