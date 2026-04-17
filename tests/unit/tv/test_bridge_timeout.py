"""Tests for TVBridgeClient timeout and error handling.

Verifies that transport-level errors (timeout, connect refused) raise
TVBridgeUnavailableError and that successful responses are passed through.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.services.tv.bridge import TVBridgeClient, TVBridgeUnavailableError


def _make_async_client_mock(
    side_effect: Exception | None = None,
    json_response: dict[str, Any] | None = None,
) -> AsyncMock:
    """Build a mock httpx.AsyncClient context manager.

    Args:
        side_effect: Exception to raise on client.get(), or None for success.
        json_response: JSON dict to return on success.

    Returns:
        AsyncMock configured as an async context manager.
    """
    client_mock = AsyncMock()
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    if side_effect is not None:
        client_mock.get = AsyncMock(side_effect=side_effect)
    else:
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.json.return_value = json_response or {}
        response_mock.raise_for_status = MagicMock()
        client_mock.get = AsyncMock(return_value=response_mock)

    return client_mock


@pytest.mark.asyncio
async def test_timeout_raises_bridge_unavailable_error() -> None:
    """TimeoutException from httpx must surface as TVBridgeUnavailableError."""
    timeout_exc = httpx.ReadTimeout(
        "timed out", request=httpx.Request("GET", "http://127.0.0.1:7100/ta_summary")
    )
    client_mock = _make_async_client_mock(side_effect=timeout_exc)

    with patch("backend.services.tv.bridge.httpx.AsyncClient", return_value=client_mock):
        bridge = TVBridgeClient()
        with pytest.raises(TVBridgeUnavailableError):
            await bridge.get_ta_summary("RELIANCE", "NSE", "1D")


@pytest.mark.asyncio
async def test_connect_error_raises_bridge_unavailable_error() -> None:
    """ConnectError from httpx must surface as TVBridgeUnavailableError."""
    connect_exc = httpx.ConnectError(
        "connect refused", request=httpx.Request("GET", "http://127.0.0.1:7100/ta_summary")
    )
    client_mock = _make_async_client_mock(side_effect=connect_exc)

    with patch("backend.services.tv.bridge.httpx.AsyncClient", return_value=client_mock):
        bridge = TVBridgeClient()
        with pytest.raises(TVBridgeUnavailableError):
            await bridge.get_ta_summary("RELIANCE", "NSE", "1D")


@pytest.mark.asyncio
async def test_success_returns_dict() -> None:
    """Successful 200 response must be returned as the parsed JSON dict."""
    expected = {"recommendation": "BUY"}
    client_mock = _make_async_client_mock(json_response=expected)

    with patch("backend.services.tv.bridge.httpx.AsyncClient", return_value=client_mock):
        bridge = TVBridgeClient()
        result = await bridge.get_ta_summary("RELIANCE", "NSE", "1D")

    assert result == expected


@pytest.mark.asyncio
async def test_screener_timeout_raises_unavailable() -> None:
    """TimeoutException on get_screener must surface as TVBridgeUnavailableError."""
    timeout_exc = httpx.ReadTimeout(
        "timed out", request=httpx.Request("GET", "http://127.0.0.1:7100/screener")
    )
    client_mock = _make_async_client_mock(side_effect=timeout_exc)

    with patch("backend.services.tv.bridge.httpx.AsyncClient", return_value=client_mock):
        bridge = TVBridgeClient()
        with pytest.raises(TVBridgeUnavailableError):
            await bridge.get_screener("INFY", "NSE")


@pytest.mark.asyncio
async def test_fundamentals_timeout_raises_unavailable() -> None:
    """TimeoutException on get_fundamentals must surface as TVBridgeUnavailableError."""
    timeout_exc = httpx.ReadTimeout(
        "timed out", request=httpx.Request("GET", "http://127.0.0.1:7100/fundamentals")
    )
    client_mock = _make_async_client_mock(side_effect=timeout_exc)

    with patch("backend.services.tv.bridge.httpx.AsyncClient", return_value=client_mock):
        bridge = TVBridgeClient()
        with pytest.raises(TVBridgeUnavailableError):
            await bridge.get_fundamentals("TCS", "NSE")
