"""Tests for GET /api/stocks/{symbol}/analysis — V11-9 punch list."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app

LEGACY_SIGNAL_KEYS = {
    "rs_composite",
    "rs_momentum",
    "rs_quadrant",
    "rsi_14",
    "adx_14",
    "macd_bullish",
    "above_200dma",
    "above_50dma",
}

OPENBB_EXTRA_KEYS = {
    "volatility_20d",
    "beta_nifty",
    "sharpe_1y",
    "sortino_1y",
    "max_drawdown_1y",
    "piotroski_score",
    "macd_line",
    "macd_signal_line",
    "bollinger_upper",
    "bollinger_lower",
    "stochastic_k",
    "stochastic_d",
    "disparity_20",
}


STOCK_DETAIL_FIXTURE: dict[str, Any] = {
    "id": "abc123",
    "symbol": "RELIANCE",
    "company_name": "Reliance Industries Ltd",
    "sector": "Energy",
    "rs_composite": "2.5",
    "rs_momentum": "1.2",
    "rsi_14": "55.3",
    "adx_14": "28.1",
    "macd_histogram": "0.45",
    "macd_line": "1.2",
    "macd_signal": "0.75",
    "above_200dma": True,
    "above_50dma": True,
    "volatility_20d": "0.023",
    "beta_nifty": "0.85",
    "sharpe_1y": "1.2",
    "sortino_1y": "1.5",
    "max_drawdown_1y": "-0.18",
    "bollinger_upper": "2800.0",
    "bollinger_lower": "2400.0",
    "stochastic_k": "65.0",
    "stochastic_d": "60.0",
    "disparity_20": "2.1",
    "rs_date": "2026-04-18",
}


def _make_db_mock() -> MagicMock:
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


def _patch_jip(stock_fixture: dict[str, Any] | None = STOCK_DETAIL_FIXTURE):
    """Patch JIPDataService.get_stock_detail in the analysis route module."""
    mock_svc = MagicMock()
    mock_svc.get_stock_detail = AsyncMock(return_value=stock_fixture)
    return patch("backend.routes.stock_analysis.JIPDataService", return_value=mock_svc)


def _patch_piotroski(score: int = 7):
    from backend.models.derived import Piotroski, PiotroskiDetail

    pio = Piotroski(score=score, grade="B", detail=PiotroskiDetail())
    return patch(
        "backend.services.analysis_service.compute_piotroski",
        AsyncMock(return_value=pio),
    )


def _patch_get_db():
    mock_db = _make_db_mock()
    return patch("backend.routes.stock_analysis.get_db", return_value=mock_db)


# ── Correctness tests ────────────────────────────────────────────────────────


class TestLegacyEngine:
    def test_returns_200_with_data_meta_envelope(self, client: TestClient) -> None:
        with _patch_jip(), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "_meta" in body

    def test_default_engine_is_legacy(self, client: TestClient) -> None:
        with _patch_jip(), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis")
        assert resp.status_code == 200
        assert resp.json()["data"]["engine"] == "legacy"

    def test_explicit_engine_legacy(self, client: TestClient) -> None:
        with _patch_jip(), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=legacy")
        assert resp.status_code == 200
        assert resp.json()["data"]["engine"] == "legacy"

    def test_legacy_signals_keys_present(self, client: TestClient) -> None:
        with _patch_jip(), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis")
        signals = resp.json()["data"]["signals"]
        for key in LEGACY_SIGNAL_KEYS:
            assert key in signals, f"Missing legacy key: {key}"

    def test_404_on_unknown_symbol(self, client: TestClient) -> None:
        with _patch_jip(None), _patch_get_db():
            resp = client.get("/api/v1/stocks/UNKNOWN_XYZ/analysis")
        assert resp.status_code == 404

    def test_400_on_invalid_engine(self, client: TestClient) -> None:
        with _patch_jip(), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=bad_engine")
        assert resp.status_code == 400

    def test_rs_quadrant_is_computed(self, client: TestClient) -> None:
        with _patch_jip(), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis")
        signals = resp.json()["data"]["signals"]
        assert signals["rs_quadrant"] in {"LEADING", "LAGGING", "IMPROVING", "WEAKENING", None}

    def test_macd_bullish_true_when_histogram_positive(self, client: TestClient) -> None:
        with _patch_jip(), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis")
        signals = resp.json()["data"]["signals"]
        # STOCK_DETAIL_FIXTURE has macd_histogram=0.45 > 0
        assert signals["macd_bullish"] is True


class TestOpenBBEngine:
    def test_returns_200_with_openbb_engine(self, client: TestClient) -> None:
        with _patch_jip(), _patch_piotroski(), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=openbb")
        assert resp.status_code == 200
        assert resp.json()["data"]["engine"] == "openbb"

    def test_openbb_contains_all_legacy_keys(self, client: TestClient) -> None:
        """Schema-diff test: openbb engine is a strict superset of legacy keys."""
        with _patch_jip(), _patch_piotroski(), _patch_get_db():
            openbb_resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=openbb")
        with _patch_jip(), _patch_get_db():
            legacy_resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=legacy")

        legacy_keys = set(legacy_resp.json()["data"]["signals"].keys())
        openbb_keys = set(openbb_resp.json()["data"]["signals"].keys())

        missing = legacy_keys - openbb_keys
        assert not missing, f"OpenBB missing legacy keys: {missing}"

    def test_openbb_has_extra_keys_beyond_legacy(self, client: TestClient) -> None:
        """OpenBB is a STRICT superset — it has more keys than legacy."""
        with _patch_jip(), _patch_piotroski(), _patch_get_db():
            openbb_resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=openbb")
        with _patch_jip(), _patch_get_db():
            legacy_resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=legacy")

        legacy_keys = set(legacy_resp.json()["data"]["signals"].keys())
        openbb_keys = set(openbb_resp.json()["data"]["signals"].keys())
        assert openbb_keys > legacy_keys, (
            "OpenBB keys must strictly include all legacy keys plus more"
        )

    def test_openbb_signals_keys_present(self, client: TestClient) -> None:
        with _patch_jip(), _patch_piotroski(), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=openbb")
        signals = resp.json()["data"]["signals"]
        for key in OPENBB_EXTRA_KEYS:
            assert key in signals, f"Missing openbb extra key: {key}"

    def test_piotroski_score_in_openbb_response(self, client: TestClient) -> None:
        with _patch_jip(), _patch_piotroski(score=6), _patch_get_db():
            resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=openbb")
        assert resp.json()["data"]["signals"]["piotroski_score"] == 6

    def test_piotroski_none_on_failure_graceful_degradation(self, client: TestClient) -> None:
        """If Piotroski computation fails, openbb engine still returns 200."""
        with _patch_jip(), _patch_get_db():
            with patch(
                "backend.services.analysis_service.compute_piotroski",
                AsyncMock(side_effect=RuntimeError("DB error")),
            ):
                resp = client.get("/api/v1/stocks/RELIANCE/analysis?engine=openbb")
        assert resp.status_code == 200
        assert resp.json()["data"]["signals"]["piotroski_score"] is None


class TestBenchmark:
    """Punch list item 2: p95 of openbb <= 1.5x p95 of legacy (100-call sequential benchmark)."""

    N_CALLS = 100
    WARMUP = 10

    def _run_timed(self, client: TestClient, url: str, n: int) -> list[float]:
        times = []
        for _ in range(n):
            t0 = time.perf_counter()
            resp = client.get(url)
            elapsed = time.perf_counter() - t0
            assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
            times.append(elapsed)
        return times

    def test_openbb_p95_within_1_5x_legacy_p95(self, client: TestClient) -> None:
        """100-call sequential benchmark: openbb p95 <= 1.5x legacy p95.

        Rate limiter disabled for this test (benchmark makes 220+ requests).
        """
        from backend.main import app as _app

        original_enabled = _app.state.limiter.enabled
        _app.state.limiter.enabled = False
        try:
            with _patch_jip(), _patch_piotroski(), _patch_get_db():
                # Warmup
                self._run_timed(client, "/api/v1/stocks/RELIANCE/analysis", self.WARMUP)
                self._run_timed(
                    client, "/api/v1/stocks/RELIANCE/analysis?engine=openbb", self.WARMUP
                )

                legacy_times = self._run_timed(
                    client, "/api/v1/stocks/RELIANCE/analysis", self.N_CALLS
                )
                openbb_times = self._run_timed(
                    client, "/api/v1/stocks/RELIANCE/analysis?engine=openbb", self.N_CALLS
                )
        finally:
            _app.state.limiter.enabled = original_enabled

        legacy_sorted = sorted(legacy_times)
        openbb_sorted = sorted(openbb_times)
        p95_legacy = legacy_sorted[int(0.95 * self.N_CALLS)]
        p95_openbb = openbb_sorted[int(0.95 * self.N_CALLS)]

        ratio = p95_openbb / p95_legacy if p95_legacy > 0 else 1.0
        assert ratio <= 1.5, (
            f"OpenBB p95={p95_openbb * 1000:.1f}ms > 1.5x legacy p95={p95_legacy * 1000:.1f}ms "
            f"(ratio={ratio:.2f})"
        )
