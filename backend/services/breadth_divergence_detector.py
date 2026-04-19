"""BreadthDivergenceDetector — V2FE-1: Detect price/breadth divergences.

Compares index price direction vs breadth (pct above 50-DMA) direction
over rolling windows. Bullish divergence: price down, breadth up.
Bearish divergence: price up, breadth down.

If de_index_daily is missing or empty, returns insufficient_data=True.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


class BreadthDivergenceDetector:
    """Detect price vs breadth divergences from de_breadth_daily + de_index_daily."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute(
        self,
        universe: str,
        window: int = 20,
        lookback: int = 3,
    ) -> dict[str, Any]:
        """Compute price/breadth divergences.

        Args:
            universe: "nifty500" or "nifty50"
            window: Rolling window in trading days (default 20)
            lookback: Lookback period in months (default 3)

        Returns:
            Dict with divergences list and _meta envelope.
        """
        t0 = time.monotonic()
        import datetime

        lookback_days = lookback * 30
        today_str = datetime.date.today().isoformat()

        # Try to get index price data
        index_rows: list[dict[str, Any]] = []
        index_data_ok = False

        try:
            # Try de_index_daily first (more reliable index data)
            # Map universe to index ticker
            index_ticker = "NIFTY 500" if universe == "nifty500" else "NIFTY 50"

            index_query = text(
                """
                SELECT date::text, close
                FROM de_index_daily
                WHERE ticker = :ticker
                  AND date >= CURRENT_DATE - INTERVAL :lookback_interval
                ORDER BY date ASC
                """
            )
            index_result = await self._session.execute(
                index_query,
                {"ticker": index_ticker, "lookback_interval": f"{lookback_days} days"},
            )
            index_raw = index_result.mappings().all()
            if index_raw:
                index_rows = [dict(r) for r in index_raw]
                index_data_ok = True

        except Exception as exc:
            log.warning(
                "breadth_divergence_index_query_failed",
                error=str(exc)[:300],
                universe=universe,
            )
            index_data_ok = False

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if not index_data_ok or not index_rows:
            return {
                "divergences": [],
                "_meta": {
                    "data_as_of": today_str,
                    "insufficient_data": True,
                    "record_count": 0,
                    "query_ms": elapsed_ms,
                    "reason": "Index price data unavailable from de_index_daily",
                },
            }

        # Get breadth data
        breadth_rows: list[dict[str, Any]] = []
        try:
            breadth_query = text(
                """
                SELECT date::text, above_dma50
                FROM de_breadth_daily
                WHERE date >= CURRENT_DATE - INTERVAL :lookback_interval
                ORDER BY date ASC
                """
            )
            breadth_result = await self._session.execute(
                breadth_query,
                {"lookback_interval": f"{lookback_days} days"},
            )
            breadth_raw = breadth_result.mappings().all()
            if breadth_raw:
                breadth_rows = [dict(r) for r in breadth_raw]
        except Exception as exc:
            log.warning(
                "breadth_divergence_breadth_query_failed",
                error=str(exc)[:300],
            )

        if not breadth_rows:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            return {
                "divergences": [],
                "_meta": {
                    "data_as_of": today_str,
                    "insufficient_data": True,
                    "record_count": 0,
                    "query_ms": elapsed_ms,
                    "reason": "Breadth data unavailable",
                },
            }

        # Align on common dates
        breadth_by_date = {r["date"]: r["above_dma50"] for r in breadth_rows}
        aligned: list[tuple[str, Decimal, int]] = []
        for row in index_rows:
            d = row["date"]
            if d in breadth_by_date and row.get("close") is not None:
                b = breadth_by_date[d]
                if b is not None:
                    aligned.append((d, Decimal(str(row["close"])), int(b)))

        divergences: list[dict[str, Any]] = []

        if len(aligned) >= window:
            for i in range(window, len(aligned)):
                start = aligned[i - window]
                end = aligned[i]

                start_date, start_price, start_breadth = start
                end_date, end_price, end_breadth = end

                if start_price == 0:
                    continue

                index_change = (end_price - start_price) / start_price * 100
                breadth_change = end_breadth - start_breadth

                # Bearish divergence: index up, breadth down
                if index_change > 0 and breadth_change < 0:
                    divergences.append(
                        {
                            "start_date": start_date,
                            "end_date": end_date,
                            "type": "bearish",
                            "index_change_pct": index_change.quantize(Decimal("0.0001")),
                            "breadth_change_pct": Decimal(str(breadth_change)).quantize(
                                Decimal("0.0001")
                            ),
                        }
                    )
                # Bullish divergence: index down, breadth up
                elif index_change < 0 and breadth_change > 0:
                    divergences.append(
                        {
                            "start_date": start_date,
                            "end_date": end_date,
                            "type": "bullish",
                            "index_change_pct": index_change.quantize(Decimal("0.0001")),
                            "breadth_change_pct": Decimal(str(breadth_change)).quantize(
                                Decimal("0.0001")
                            ),
                        }
                    )

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        data_as_of = aligned[-1][0] if aligned else today_str

        log.info(
            "breadth_divergence_computed",
            universe=universe,
            window=window,
            lookback=lookback,
            divergence_count=len(divergences),
            query_ms=elapsed_ms,
        )

        return {
            "divergences": divergences,
            "_meta": {
                "data_as_of": data_as_of,
                "insufficient_data": False,
                "record_count": len(divergences),
                "query_ms": elapsed_ms,
            },
        }
