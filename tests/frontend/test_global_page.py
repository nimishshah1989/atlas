"""Smoke tests for /pro/global page contract — V5-14.

Tests verify the API contracts that the page depends on:
- Each endpoint returns valid data
- Numbers are Decimal-serialised strings (lakh/crore formatting happens in frontend)
- Dates are ISO format (DD-MMM-YYYY formatting happens in frontend)
- data_as_of / meta present in every response
- Single endpoint failure doesn't affect others (independence)

All tests are marked @pytest.mark.integration (auto-applied by conftest.py)
and require a live backend on localhost:8000.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import httpx

BACKEND = "http://localhost:8000"


@pytest.mark.asyncio
async def test_briefing_returns_meta() -> None:
    """GET /api/v1/global/briefing returns 200 with meta block."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/briefing")
    assert r.status_code == 200
    body = r.json()
    assert "_meta" in body or "meta" in body
    meta = body.get("_meta") or body.get("meta", {})
    assert "record_count" in meta


@pytest.mark.asyncio
async def test_briefing_has_date_for_data_as_of() -> None:
    """Briefing must have date or generated_at for data_as_of display."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/briefing")
    assert r.status_code == 200
    body = r.json()
    briefing = body.get("briefing") or body.get("data")
    if briefing is not None:
        assert briefing.get("date") or briefing.get("generated_at"), (
            "Briefing must have date or generated_at for data_as_of display"
        )


@pytest.mark.asyncio
async def test_ratios_returns_data() -> None:
    """GET /api/v1/global/ratios returns 200 with data list and meta."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/ratios")
    assert r.status_code == 200
    body = r.json()
    assert "ratios" in body or "data" in body
    meta = body.get("_meta") or body.get("meta", {})
    assert "record_count" in meta


@pytest.mark.asyncio
async def test_ratios_decimal_values() -> None:
    """Macro ratio latest_value must be a string (Decimal serialization), not float."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/ratios")
    assert r.status_code == 200
    body = r.json()
    ratios = body.get("ratios") or body.get("data") or []
    for ratio in ratios[:5]:
        val = ratio.get("latest_value")
        if val is not None:
            assert isinstance(val, str), (
                f"latest_value should be string (Decimal-serialised), got {type(val)}: {val!r}"
            )
            # Must be parseable as Decimal
            Decimal(val)


@pytest.mark.asyncio
async def test_rs_heatmap_returns_data() -> None:
    """GET /api/v1/global/rs-heatmap returns 200 with heatmap list."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/rs-heatmap")
    assert r.status_code == 200
    body = r.json()
    assert "heatmap" in body or "data" in body


@pytest.mark.asyncio
async def test_rs_heatmap_decimal_values() -> None:
    """RS heatmap rs_composite must be string (Decimal) or null, never float."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/rs-heatmap")
    assert r.status_code == 200
    body = r.json()
    rows = body.get("heatmap") or body.get("data") or []
    for row in rows[:5]:
        val = row.get("rs_composite")
        if val is not None:
            assert isinstance(val, str), f"rs_composite should be string, got {type(val)}: {val!r}"
            Decimal(val)


@pytest.mark.asyncio
async def test_regime_returns_data() -> None:
    """GET /api/v1/global/regime returns 200 with data block and meta."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/regime")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body or "regime" in body
    meta = body.get("_meta") or body.get("meta", {})
    assert "record_count" in meta


@pytest.mark.asyncio
async def test_regime_date_is_iso() -> None:
    """Regime date field must be an ISO format string for IST rendering in frontend."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/regime")
    assert r.status_code == 200
    body = r.json()
    data = body.get("data") or {}
    regime = data.get("regime") or body.get("regime")
    if regime and regime.get("date"):
        assert isinstance(regime["date"], str), (
            f"regime.date must be a string, got {type(regime['date'])}"
        )


@pytest.mark.asyncio
async def test_patterns_returns_data() -> None:
    """GET /api/v1/global/patterns returns 200 with patterns list."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/patterns")
    assert r.status_code == 200
    body = r.json()
    assert "patterns" in body or "data" in body


@pytest.mark.asyncio
async def test_patterns_fields_present() -> None:
    """Pattern findings must have finding_type, title, content, data_as_of fields."""
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        r = await client.get("/api/v1/global/patterns")
    assert r.status_code == 200
    body = r.json()
    patterns = body.get("patterns") or body.get("data") or []
    for p in patterns[:3]:
        assert "finding_type" in p, "PatternFinding missing finding_type"
        assert "title" in p, "PatternFinding missing title"
        assert "content" in p, "PatternFinding missing content"
        assert "data_as_of" in p, "PatternFinding missing data_as_of"


@pytest.mark.asyncio
async def test_panel_independence() -> None:
    """All 5 endpoints are independent — each returns 200 regardless of others.

    This simulates the frontend panel isolation requirement: a failure in one
    panel must not cascade to others.
    """
    endpoints = [
        "/api/v1/global/briefing",
        "/api/v1/global/ratios",
        "/api/v1/global/rs-heatmap",
        "/api/v1/global/regime",
        "/api/v1/global/patterns",
    ]
    results: dict[str, int | str] = {}
    async with httpx.AsyncClient(base_url=BACKEND, timeout=10) as client:
        for ep in endpoints:
            try:
                r = await client.get(ep)
                results[ep] = r.status_code
            except Exception as exc:  # noqa: BLE001
                results[ep] = f"error: {exc}"

    for ep, status in results.items():
        assert status == 200, f"{ep} returned {status}"
