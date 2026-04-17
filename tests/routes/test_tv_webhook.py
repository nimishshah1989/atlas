"""Route tests for POST /api/webhooks/tradingview.

Tests use ASGITransport + AsyncClient against the FastAPI app — no live
server needed. DB session is overridden via dependency_overrides.
TVCacheService.upsert is patched so no real DB writes occur.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app
from backend.models.tv import TvCacheEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_db_session() -> AsyncMock:
    """Return an AsyncMock suitable as an injected DB session."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    return session


def _mock_cache_entry(symbol: str = "RELIANCE", data_type: str = "ta_summary") -> TvCacheEntry:
    return TvCacheEntry(
        symbol=symbol,
        exchange="NSE",
        data_type=data_type,
        interval="none",
        tv_data={"recommendation": "BUY"},
        fetched_at=datetime.now(tz=UTC),
        is_stale=False,
    )


VALID_PAYLOAD = {
    "symbol": "RELIANCE",
    "exchange": "NSE",
    "data_type": "ta_summary",
    "interval": "1D",
    "tv_payload": {"recommendation": "BUY", "buy": 10, "sell": 2},
}


# ---------------------------------------------------------------------------
# Helper to build an AsyncClient with DB override
# ---------------------------------------------------------------------------


def _make_client() -> AsyncClient:
    app.dependency_overrides[get_db] = _mock_db_session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_payload_and_secret_returns_200() -> None:
    """POST with valid secret and well-formed body must return 200."""
    mock_entry = _mock_cache_entry()
    with patch("backend.routes.webhooks.TVCacheService") as MockSvc:
        instance = MockSvc.return_value
        instance.upsert = AsyncMock(return_value=mock_entry)
        with patch("backend.routes.webhooks.get_settings") as mock_settings:
            settings = MagicMock()
            settings.tv_webhook_secret = "tok_abc"
            mock_settings.return_value = settings
            async with _make_client() as ac:
                resp = await ac.post(
                    "/api/webhooks/tradingview",
                    json=VALID_PAYLOAD,
                    headers={"X-TV-Signature": "tok_abc"},
                )

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["status"] == "ok"
    assert body["data"]["symbol"] == "RELIANCE"
    assert "_meta" in body


@pytest.mark.asyncio
async def test_missing_signature_header_returns_403() -> None:
    """POST without X-TV-Signature header must return 403."""
    with patch("backend.routes.webhooks.get_settings") as mock_settings:
        settings = MagicMock()
        settings.tv_webhook_secret = "tok_abc"
        mock_settings.return_value = settings
        async with _make_client() as ac:
            resp = await ac.post(
                "/api/webhooks/tradingview",
                json=VALID_PAYLOAD,
                # No X-TV-Signature header
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_wrong_signature_returns_403() -> None:
    """POST with an incorrect X-TV-Signature must return 403."""
    with patch("backend.routes.webhooks.get_settings") as mock_settings:
        settings = MagicMock()
        settings.tv_webhook_secret = "tok_xyz"
        mock_settings.return_value = settings
        async with _make_client() as ac:
            resp = await ac.post(
                "/api/webhooks/tradingview",
                json=VALID_PAYLOAD,
                headers={"X-TV-Signature": "wrong-secret"},
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_malformed_json_body_returns_400() -> None:
    """POST with a body missing required fields must return 400.

    The global validation_error_handler (§20.5) converts Pydantic 422 →
    400 so all validation errors have the same error-envelope shape.
    """
    with patch("backend.routes.webhooks.get_settings") as mock_settings:
        settings = MagicMock()
        settings.tv_webhook_secret = "tok_abc"
        mock_settings.return_value = settings
        async with _make_client() as ac:
            # Missing required 'symbol' and 'data_type' fields
            resp = await ac.post(
                "/api/webhooks/tradingview",
                json={"exchange": "NSE"},
                headers={"X-TV-Signature": "tok_abc"},
            )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_valid_payload_calls_cache_upsert() -> None:
    """POST with valid secret must call TVCacheService.upsert exactly once."""
    mock_entry = _mock_cache_entry()
    with patch("backend.routes.webhooks.TVCacheService") as MockSvc:
        instance = MockSvc.return_value
        instance.upsert = AsyncMock(return_value=mock_entry)
        with patch("backend.routes.webhooks.get_settings") as mock_settings:
            settings = MagicMock()
            settings.tv_webhook_secret = "tok_abc"
            mock_settings.return_value = settings
            async with _make_client() as ac:
                await ac.post(
                    "/api/webhooks/tradingview",
                    json=VALID_PAYLOAD,
                    headers={"X-TV-Signature": "tok_abc"},
                )

        instance.upsert.assert_called_once()
        call_kwargs = instance.upsert.call_args
        assert call_kwargs.kwargs["symbol"] == "RELIANCE"
        assert call_kwargs.kwargs["data_type"] == "ta_summary"


@pytest.mark.asyncio
async def test_empty_symbol_returns_400() -> None:
    """POST with an empty symbol string must return 400.

    Pydantic raises a validation error (min_length=1 violated), which the
    global validation_error_handler (§20.5) converts to 400.
    """
    bad_payload = {**VALID_PAYLOAD, "symbol": ""}
    with patch("backend.routes.webhooks.get_settings") as mock_settings:
        settings = MagicMock()
        settings.tv_webhook_secret = "tok_abc"
        mock_settings.return_value = settings
        async with _make_client() as ac:
            resp = await ac.post(
                "/api/webhooks/tradingview",
                json=bad_payload,
                headers={"X-TV-Signature": "tok_abc"},
            )

    assert resp.status_code == 400
