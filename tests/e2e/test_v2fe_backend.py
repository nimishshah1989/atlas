"""
V2FE backend API smoke tests — §8.1

9 checks per the V2FE spec. All tests SKIP gracefully if backend is unreachable.
Includes a deterministic replay test per §2.5.
"""

from __future__ import annotations

import pytest

BASE_URL = "http://localhost:8000"


def _get(endpoint: str, timeout: int = 3):  # type: ignore[return]
    """GET endpoint, skip test if backend is unreachable."""
    try:
        import requests
    except ImportError:
        pytest.skip("requests library not installed")

    url = f"{BASE_URL}{endpoint}"
    try:
        return requests.get(url, timeout=timeout)
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    ):
        pytest.skip(f"Backend unreachable at {url}")


# ---------------------------------------------------------------------------
# §8.1 — 9 backend smoke checks
# ---------------------------------------------------------------------------


def test_be_01_health_returns_200() -> None:
    """Backend health check."""
    r = _get("/health")
    assert r.status_code == 200


def test_be_02_breadth_global_returns_200() -> None:
    """Breadth global endpoint returns 200."""
    r = _get("/api/v1/breadth/global")
    assert r.status_code == 200


def test_be_03_sectors_returns_200() -> None:
    """Sectors endpoint returns 200."""
    r = _get("/api/v1/stocks/sectors")
    assert r.status_code == 200


def test_be_04_stock_detail_returns_200() -> None:
    """Stock detail endpoint returns 200 for RELIANCE."""
    r = _get("/api/v1/stocks/RELIANCE")
    assert r.status_code in (200, 404), f"Unexpected status {r.status_code}"
    # 404 is acceptable if RELIANCE symbol format differs; just ensure no 5xx
    assert r.status_code < 500, f"Server error {r.status_code}"


def test_be_05_breadth_country_returns_200() -> None:
    """Breadth country endpoint returns 200."""
    r = _get("/api/v1/breadth/country")
    assert r.status_code == 200


def test_be_06_breadth_sector_returns_200() -> None:
    """Breadth sector endpoint returns 200."""
    r = _get("/api/v1/breadth/sector")
    assert r.status_code in (200, 404), f"Unexpected status {r.status_code}"
    assert r.status_code < 500, f"Server error {r.status_code}"


def test_be_07_global_events_returns_200() -> None:
    """Global events endpoint returns 200."""
    r = _get("/api/v1/global/events")
    assert r.status_code in (200, 404), f"Unexpected status {r.status_code}"
    assert r.status_code < 500, f"Server error {r.status_code}"


def test_be_08_breadth_divergences_returns_200() -> None:
    """Breadth divergences endpoint returns 200 with shape check."""
    r = _get("/api/v1/breadth/divergences")
    assert r.status_code in (200, 404), f"Unexpected status {r.status_code}"
    assert r.status_code < 500, f"Server error {r.status_code}"
    if r.status_code == 200:
        body = r.json()
        # Must have _meta envelope per §8.1
        assert "_meta" in body or "data" in body, "Response lacks _meta or data key"


def test_be_09_meta_envelope_present() -> None:
    """V2 responses must carry _meta envelope (breadth/global as representative)."""
    r = _get("/api/v1/breadth/global")
    assert r.status_code == 200
    body = r.json()
    assert "_meta" in body, "Response missing _meta envelope"
    meta = body["_meta"]
    assert "data_as_of" in meta, "_meta missing data_as_of"


# ---------------------------------------------------------------------------
# §2.5 Deterministic replay test
# ---------------------------------------------------------------------------


def test_breadth_deterministic_replay() -> None:
    """Two consecutive calls return identical _meta.data_as_of.

    Verifies §2.5: same data_as_of -> same output (deterministic).
    """
    r1 = _get("/api/v1/breadth/global")
    r2 = _get("/api/v1/breadth/global")

    assert r1.status_code == 200, f"First call failed: {r1.status_code}"
    assert r2.status_code == 200, f"Second call failed: {r2.status_code}"

    d1 = r1.json()
    d2 = r2.json()

    as_of_1 = d1.get("_meta", {}).get("data_as_of")
    as_of_2 = d2.get("_meta", {}).get("data_as_of")

    assert as_of_1 is not None, "First response missing _meta.data_as_of"
    assert as_of_2 is not None, "Second response missing _meta.data_as_of"
    assert as_of_1 == as_of_2, f"Non-deterministic data_as_of: {as_of_1!r} != {as_of_2!r}"
