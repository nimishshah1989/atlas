"""TV bridge — direct tradingview_screener library integration.

Previously wrapped an HTTP sidecar; now queries TradingView in-process.
TVBridgeUnavailableError is raised when the TradingView API is unreachable
or the symbol is not found, so callers remain unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class TVBridgeUnavailableError(Exception):
    """Raised when TradingView data cannot be fetched."""


_TA_COLUMNS = [
    "name",
    "Recommend.All",
    "Recommend.MA",
    "Recommend.Other",
    "RSI",
    "RSI[1]",
    "MACD.macd",
    "MACD.signal",
    "EMA200",
    "SMA20",
    "BB.upper",
    "BB.lower",
    "close",
    "volume",
]

_SCREENER_COLUMNS = [
    "name",
    "close",
    "volume",
    "market_cap_basic",
    "price_earnings_ttm",
    "earnings_per_share_basic_ttm",
    "52_week_high",
    "52_week_low",
]

_FUNDAMENTAL_COLUMNS = [
    "name",
    "earnings_per_share_basic_ttm",
    "price_earnings_ttm",
    "price_to_book_ratio",
    "debt_to_equity",
    "return_on_equity",
    "gross_margin",
    "net_margin",
    "revenue_per_employee",
    "market_cap_basic",
]


class TVBridgeClient:
    """In-process TradingView data client using tradingview_screener library."""

    async def get_ta_summary(
        self,
        symbol: str,
        exchange: str,
        interval: str,
    ) -> dict[str, Any]:
        """Fetch TA summary for a symbol.

        Args:
            symbol: Ticker (e.g. 'RELIANCE').
            exchange: Exchange code (e.g. 'NSE') — used to prefix ticker.
            interval: Ignored in library mode (library returns daily data).

        Returns:
            Dict with TA fields.

        Raises:
            TVBridgeUnavailableError: If symbol not found or network error.
        """
        return await self._fetch(symbol, exchange, _TA_COLUMNS)

    async def get_screener(
        self,
        symbol: str,
        exchange: str,
    ) -> dict[str, Any]:
        """Fetch screener data for a symbol."""
        return await self._fetch(symbol, exchange, _SCREENER_COLUMNS)

    async def get_fundamentals(
        self,
        symbol: str,
        exchange: str,
    ) -> dict[str, Any]:
        """Fetch fundamentals data for a symbol."""
        return await self._fetch(symbol, exchange, _FUNDAMENTAL_COLUMNS)

    async def _fetch(
        self,
        symbol: str,
        exchange: str,
        columns: list[str],
    ) -> dict[str, Any]:
        try:
            from tradingview_screener.query import Query  # lazy import

            ticker = f"{exchange}:{symbol}"

            def _run_query() -> dict[str, Any]:
                _, df = (
                    Query().select(*columns).set_tickers(ticker).set_markets("india")
                ).get_scanner_data()
                if df.empty:
                    raise TVBridgeUnavailableError(f"Symbol {ticker!r} not found in TradingView")
                row: dict[str, Any] = df.iloc[0].to_dict()
                return row

            fetched = await asyncio.to_thread(_run_query)
            log.debug("tv_bridge_fetch_ok", symbol=symbol, columns=len(columns))
            return fetched
        except TVBridgeUnavailableError:
            raise
        except Exception as exc:
            log.warning("tv_bridge_fetch_error", symbol=symbol, error=str(exc))
            raise TVBridgeUnavailableError(f"TradingView fetch failed for {symbol}: {exc}") from exc
