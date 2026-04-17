"""Route tests for GET /api/v1/sentiment/composite (C-DER-3).

Uses ASGI transport + dependency_overrides[get_db].
Mocks compute_sentiment_composite at the route module level.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app
from backend.models.schemas import (
    ResponseMeta,
    SentimentComponent,
    SentimentResponse,
    SentimentZone,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TODAY = datetime.date(2026, 4, 17)

_SENTIMENT_RESPONSE_FIXTURE = SentimentResponse(
    composite_score=Decimal("52.3"),
    zone=SentimentZone.NEUTRAL,
    components=[
        SentimentComponent(
            name="Price Breadth",
            score=Decimal("65.0"),
            weight=Decimal("0.6"),
            available=True,
            note=None,
        ),
        SentimentComponent(
            name="Options/PCR",
            score=None,
            weight=Decimal("0.0"),
            available=False,
            note="PCR data unavailable — pipeline gap",
        ),
        SentimentComponent(
            name="Institutional Flow",
            score=None,
            weight=Decimal("0.0"),
            available=False,
            note="FII flow data unavailable — pipeline gap",
        ),
        SentimentComponent(
            name="Fundamental Revisions",
            score=Decimal("28.5"),
            weight=Decimal("0.4"),
            available=True,
            note=None,
        ),
    ],
    weight_redistribution_active=True,
    as_of=_TODAY,
    meta=ResponseMeta(record_count=4, query_ms=18),
)


def _mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Test: GET /api/v1/sentiment/composite → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentiment_route_200() -> None:
    """GET /api/v1/sentiment/composite → 200 with all required fields."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    try:
        with patch(
            "backend.routes.sentiment.compute_sentiment_composite",
            new=AsyncMock(return_value=_SENTIMENT_RESPONSE_FIXTURE),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/sentiment/composite")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()

    # Required keys per spec
    assert "composite_score" in body, "Response must contain 'composite_score'"
    assert "zone" in body, "Response must contain 'zone'"
    assert "components" in body, "Response must contain 'components'"
    assert "weight_redistribution_active" in body, (
        "Response must contain 'weight_redistribution_active'"
    )
    assert "as_of" in body, "Response must contain 'as_of'"
    assert "meta" in body, "Response must contain 'meta'"

    # Components structure
    assert len(body["components"]) == 4, (
        f"Must have exactly 4 components, got {len(body['components'])}"
    )

    # Verify specific values
    assert body["weight_redistribution_active"] is True
    assert body["zone"] == "NEUTRAL"
    assert float(body["composite_score"]) == pytest.approx(52.3, rel=0.01)

    # Verify component names
    names = {c["name"] for c in body["components"]}
    assert "Price Breadth" in names
    assert "Options/PCR" in names
    assert "Institutional Flow" in names
    assert "Fundamental Revisions" in names

    # Verify PCR and Flow are unavailable with pipeline gap notes
    pcr = next(c for c in body["components"] if c["name"] == "Options/PCR")
    assert pcr["available"] is False
    assert "pipeline gap" in pcr["note"].lower()

    flow = next(c for c in body["components"] if c["name"] == "Institutional Flow")
    assert flow["available"] is False
    assert "pipeline gap" in flow["note"].lower()


@pytest.mark.asyncio
async def test_sentiment_route_503_when_breadth_missing() -> None:
    """When compute_sentiment_composite raises HTTPException(503), route propagates 503."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    try:
        with patch(
            "backend.routes.sentiment.compute_sentiment_composite",
            new=AsyncMock(side_effect=HTTPException(503, detail="Breadth data not available")),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/sentiment/composite")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503, f"Expected 503, got {response.status_code}"


@pytest.mark.asyncio
async def test_sentiment_route_returns_null_composite_when_all_unavailable() -> None:
    """When composite_score=None and zone=None, route serializes them as null."""
    null_response = SentimentResponse(
        composite_score=None,
        zone=None,
        components=[
            SentimentComponent(
                name="Price Breadth",
                score=None,
                weight=Decimal("0.6"),
                available=True,
                note=None,
            ),
            SentimentComponent(
                name="Options/PCR",
                score=None,
                weight=Decimal("0.0"),
                available=False,
                note="PCR data unavailable — pipeline gap",
            ),
            SentimentComponent(
                name="Institutional Flow",
                score=None,
                weight=Decimal("0.0"),
                available=False,
                note="FII flow data unavailable — pipeline gap",
            ),
            SentimentComponent(
                name="Fundamental Revisions",
                score=None,
                weight=Decimal("0.4"),
                available=False,
                note="Fundamentals data unavailable",
            ),
        ],
        weight_redistribution_active=True,
        as_of=None,
        meta=ResponseMeta(record_count=4, query_ms=5),
    )

    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    try:
        with patch(
            "backend.routes.sentiment.compute_sentiment_composite",
            new=AsyncMock(return_value=null_response),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/sentiment/composite")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["composite_score"] is None
    assert body["zone"] is None
    assert body["weight_redistribution_active"] is True
