"""Integration tests for Alerts API routes (V6-7).

These tests hit the live backend at http://localhost:8010.
Auto-marked as ``integration`` by tests/api/conftest.py.
Uses the ``api_client`` fixture from conftest.

Run with: pytest tests/api/test_alerts.py -v --tb=short
(Skipped automatically when backend is unreachable.)
"""

from __future__ import annotations

import httpx


# ---------------------------------------------------------------------------
# 1. GET /api/alerts returns 200 with data list and _meta
# ---------------------------------------------------------------------------


def test_list_alerts_returns_200(api_client: httpx.Client) -> None:
    """GET /api/alerts returns 200 with data list and _meta envelope."""
    resp = api_client.get("/api/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "_meta" in body
    assert isinstance(body["data"], list)
    meta = body["_meta"]
    assert "returned" in meta
    assert "offset" in meta
    assert "limit" in meta
    assert "has_more" in meta


# ---------------------------------------------------------------------------
# 2. GET /api/alerts?unread=true returns 200 (may be empty)
# ---------------------------------------------------------------------------


def test_list_alerts_unread_filter_returns_200(api_client: httpx.Client) -> None:
    """GET /api/alerts?unread=true returns 200 with only unread rows (or empty)."""
    resp = api_client.get("/api/alerts?unread=true")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    # Every returned row must be unread
    for item in body["data"]:
        assert item["is_read"] is False


# ---------------------------------------------------------------------------
# 3. POST /api/alerts/999999/read returns 404
# ---------------------------------------------------------------------------


def test_mark_nonexistent_alert_read_returns_404(api_client: httpx.Client) -> None:
    """POST /api/alerts/999999/read → 404 for missing alert."""
    resp = api_client.post("/api/alerts/999999/read")
    assert resp.status_code == 404
