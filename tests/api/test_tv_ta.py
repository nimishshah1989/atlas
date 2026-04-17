"""Live integration tests for TV TA + screener + fundamentals routes.

Marked as integration — run only with live backend:
    pytest tests/api/test_tv_ta.py -v

Skipped automatically during forge-ship gate (pytest -m 'not integration').
The tests/api/conftest.py auto-marks all tests in this directory as
integration, so no manual @pytest.mark.integration is needed here.
"""

from __future__ import annotations

import httpx
import pytest

BASE_URL = "http://localhost:8010"


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    """Synchronous client; skips if backend unreachable."""
    c = httpx.Client(base_url=BASE_URL, timeout=10.0)
    try:
        c.get("/api/v1/health")
    except httpx.ConnectError as exc:
        pytest.skip(f"backend not reachable at {BASE_URL}: {exc}")
    return c


def test_tv_ta_hdfcbank_has_required_fields(client: httpx.Client) -> None:
    """GET /api/tv/ta/HDFCBANK returns 200 or 503 with correct shape."""
    resp = client.get("/api/tv/ta/HDFCBANK")
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "recommendation_1d" in body["data"]
        assert "oscillator_score" in body["data"]
        assert "ma_score" in body["data"]
        assert "_meta" in body
        assert "is_stale" in body["_meta"]
        assert "data_as_of" in body["_meta"]


def test_tv_ta_meta_has_is_stale(client: httpx.Client) -> None:
    """GET /api/tv/ta/RELIANCE _meta includes is_stale."""
    resp = client.get("/api/tv/ta/RELIANCE")
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        body = resp.json()
        assert "is_stale" in body.get("_meta", {})


def test_tv_screener_returns_data_shape(client: httpx.Client) -> None:
    """GET /api/tv/screener/RELIANCE returns 200 or 503 with data.symbol."""
    resp = client.get("/api/tv/screener/RELIANCE")
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "symbol" in body["data"]
        assert "raw" in body["data"]


def test_tv_fundamentals_returns_data_shape(client: httpx.Client) -> None:
    """GET /api/tv/fundamentals/RELIANCE returns 200 or 503 with data.symbol."""
    resp = client.get("/api/tv/fundamentals/RELIANCE")
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "symbol" in body["data"]
        assert "raw" in body["data"]
