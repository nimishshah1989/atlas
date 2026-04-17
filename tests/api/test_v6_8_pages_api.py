"""Integration tests for V6-8 Pro pages API contracts.

Validates the shape of the backend responses consumed by /pro/alerts and
/pro/watchlists pages.  All tests hit the live backend on localhost:8010.
Auto-marked as ``integration`` by tests/api/conftest.py.
Skipped automatically when the backend is unreachable.

Run with:
    pytest tests/api/test_v6_8_pages_api.py -v --tb=short
"""

from __future__ import annotations

import httpx


# ---------------------------------------------------------------------------
# Alerts API shape tests
# ---------------------------------------------------------------------------


def test_list_alerts_page_shape(api_client: httpx.Client) -> None:
    """GET /api/alerts returns 200 with data list and _meta with required keys."""
    resp = api_client.get("/api/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body, "response must contain 'data' key"
    assert "_meta" in body, "response must contain '_meta' key"
    assert isinstance(body["data"], list), "'data' must be a list"
    meta = body["_meta"]
    for key in ("returned", "offset", "limit", "has_more"):
        assert key in meta, f"_meta must contain '{key}'"


def test_list_alerts_source_filter(api_client: httpx.Client) -> None:
    """GET /api/alerts?source=rs_analyzer returns 200 with a list (may be empty)."""
    resp = api_client.get("/api/alerts?source=rs_analyzer")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert isinstance(body["data"], list)


def test_list_alerts_unread_filter(api_client: httpx.Client) -> None:
    """GET /api/alerts?unread=true returns 200; all items must have is_read=False."""
    resp = api_client.get("/api/alerts?unread=true")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    for item in body["data"]:
        assert item["is_read"] is False, (
            f"Alert id={item.get('id')} has is_read={item.get('is_read')} "
            "but unread=true filter was applied"
        )


def test_mark_alert_read_404(api_client: httpx.Client) -> None:
    """POST /api/alerts/999999/read returns 404 for a non-existent alert."""
    resp = api_client.post("/api/alerts/999999/read")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Watchlists API shape tests
# ---------------------------------------------------------------------------


def test_list_watchlists_page_shape(api_client: httpx.Client) -> None:
    """GET /api/v1/watchlists/ returns 200 with watchlists list and total integer."""
    resp = api_client.get("/api/v1/watchlists/")
    assert resp.status_code == 200
    body = resp.json()
    assert "watchlists" in body, "response must contain 'watchlists' key"
    assert "total" in body, "response must contain 'total' key"
    assert isinstance(body["watchlists"], list), "'watchlists' must be a list"
    assert isinstance(body["total"], int), "'total' must be an integer"


def test_sync_nonexistent_watchlist_404(api_client: httpx.Client) -> None:
    """POST /api/v1/watchlists/{zero-uuid}/sync-tv returns 404."""
    zero_uuid = "00000000-0000-0000-0000-000000000000"
    resp = api_client.post(f"/api/v1/watchlists/{zero_uuid}/sync-tv")
    assert resp.status_code == 404
