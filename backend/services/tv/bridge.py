"""TV MCP bridge client — wraps the local TradingView MCP Node.js sidecar.

The sidecar runs on the same EC2 at a local port (default 7100). This module
provides an async HTTP wrapper that converts transport errors into
TVBridgeUnavailableError so callers never see raw httpx exceptions.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


class TVBridgeUnavailableError(Exception):
    """Raised when the TV MCP sidecar is unreachable or timed out."""


class TVBridgeClient:
    """Async HTTP client wrapping the TradingView MCP sidecar.

    Args:
        base_url: Base URL of the local MCP sidecar. Default: http://127.0.0.1:7100
        timeout: HTTP request timeout in seconds. Default: 10.0
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:7100",
        timeout_secs: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_secs = timeout_secs

    async def get_ta_summary(
        self,
        symbol: str,
        exchange: str,
        interval: str,
    ) -> dict[str, Any]:
        """Fetch technical analysis summary from the MCP sidecar.

        Args:
            symbol: Ticker symbol (e.g. "RELIANCE").
            exchange: Exchange code (e.g. "NSE").
            interval: Chart interval (e.g. "1D", "1W", "1M").

        Returns:
            Dict of TA summary data as returned by the sidecar.

        Raises:
            TVBridgeUnavailableError: If the sidecar is unreachable or times out.
        """
        url = f"{self.base_url}/ta_summary"
        params = {"symbol": symbol, "exchange": exchange, "interval": interval}
        log.debug(
            "tv_bridge_ta_summary_request",
            symbol=symbol,
            exchange=exchange,
            interval=interval,
        )
        return await self._get(url, params)

    async def get_screener(
        self,
        symbol: str,
        exchange: str,
    ) -> dict[str, Any]:
        """Fetch screener data from the MCP sidecar.

        Args:
            symbol: Ticker symbol (e.g. "RELIANCE").
            exchange: Exchange code (e.g. "NSE").

        Returns:
            Dict of screener data as returned by the sidecar.

        Raises:
            TVBridgeUnavailableError: If the sidecar is unreachable or times out.
        """
        url = f"{self.base_url}/screener"
        params = {"symbol": symbol, "exchange": exchange}
        log.debug("tv_bridge_screener_request", symbol=symbol, exchange=exchange)
        return await self._get(url, params)

    async def get_fundamentals(
        self,
        symbol: str,
        exchange: str,
    ) -> dict[str, Any]:
        """Fetch fundamentals data from the MCP sidecar.

        Args:
            symbol: Ticker symbol (e.g. "RELIANCE").
            exchange: Exchange code (e.g. "NSE").

        Returns:
            Dict of fundamentals data as returned by the sidecar.

        Raises:
            TVBridgeUnavailableError: If the sidecar is unreachable or times out.
        """
        url = f"{self.base_url}/fundamentals"
        params = {"symbol": symbol, "exchange": exchange}
        log.debug("tv_bridge_fundamentals_request", symbol=symbol, exchange=exchange)
        return await self._get(url, params)

    async def _get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        """Perform a GET request to the sidecar, wrapping transport errors.

        Args:
            url: Full URL to request.
            params: Query parameters to include.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            TVBridgeUnavailableError: On timeout or connection failure.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout_secs) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                log.debug("tv_bridge_response_ok", url=url, status=response.status_code)
                return payload
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            log.warning(
                "tv_bridge_unavailable",
                url=url,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise TVBridgeUnavailableError(f"TV MCP sidecar unavailable at {url}: {exc}") from exc
