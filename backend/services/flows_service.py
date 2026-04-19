"""FlowsService — V2FE-1: FII/DII flow data from de_fii_dii_daily.

Inline DB health gate: COUNT(*) probe before any data query.
Returns Decimal for all financial values (INR crore at API boundary).
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

_VALID_SCOPES = {"fii_equity", "dii_equity", "fii_debt", "dii_debt"}

_RANGE_DAYS: dict[str, int] = {
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "2y": 730,
    "5y": 1825,
}


class FlowsService:
    """Reads FII/DII flow data from de_fii_dii_daily."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_flows(
        self,
        scope: Optional[str] = None,
        range_: str = "1y",
    ) -> dict[str, Any]:
        """Return FII/DII flow series.

        Args:
            scope: Comma-separated scope values e.g. "fii_equity,dii_equity"
            range_: Date range string "1m", "3m", "6m", "1y", "2y", "5y"

        Returns:
            Dict with series list and _meta envelope.
        """
        t0 = time.monotonic()
        import datetime

        today_str = datetime.date.today().isoformat()

        # Inline DB health gate
        try:
            count_result = await self._session.execute(
                text("SELECT COUNT(*) FROM de_fii_dii_daily")
            )
            row_count = count_result.scalar_one_or_none() or 0
        except Exception as exc:
            log.warning("flows_service_health_probe_failed", error=str(exc)[:300])
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            return {
                "_meta": {
                    "data_as_of": None,
                    "insufficient_data": True,
                    "record_count": 0,
                    "query_ms": elapsed_ms,
                    "reason": "Health probe failed",
                },
                "series": [],
            }

        if row_count == 0:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            log.warning("flows_service_table_empty", table="de_fii_dii_daily")
            return {
                "_meta": {
                    "data_as_of": None,
                    "insufficient_data": True,
                    "record_count": 0,
                    "query_ms": elapsed_ms,
                    "reason": "de_fii_dii_daily has 0 rows",
                },
                "series": [],
            }

        # Determine scope columns
        if scope:
            scope_list = [
                s.strip() for s in scope.split(",") if s.strip() and s.strip() in _VALID_SCOPES
            ]
        else:
            scope_list = list(_VALID_SCOPES)

        if not scope_list:
            scope_list = list(_VALID_SCOPES)

        # Determine date range
        days = _RANGE_DAYS.get(range_, 365)

        # Build query — select all relevant columns
        series: list[dict[str, Any]] = []
        data_as_of: Optional[str] = None

        try:
            query = text(
                """
                SELECT
                    date::text,
                    fii_equity,
                    dii_equity,
                    fii_debt,
                    dii_debt
                FROM de_fii_dii_daily
                WHERE date >= CURRENT_DATE - INTERVAL :range_interval
                ORDER BY date ASC
                """
            )
            query_result = await self._session.execute(query, {"range_interval": f"{days} days"})
            rows = query_result.mappings().all()

            for row in rows:
                row_date = row["date"]
                if data_as_of is None or row_date > data_as_of:
                    data_as_of = row_date

                for sc in scope_list:
                    raw_val = row.get(sc)
                    if raw_val is None:
                        continue
                    series.append(
                        {
                            "date": row_date,
                            "scope": sc,
                            "value_crore": Decimal(str(raw_val)),
                        }
                    )

        except Exception as exc:
            log.warning("flows_service_query_failed", error=str(exc)[:300])

        # Sort ascending by date
        series.sort(key=lambda x: (x["date"], x["scope"]))

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "flows_service_fetched",
            scope=scope,
            range_=range_,
            series_count=len(series),
            query_ms=elapsed_ms,
        )

        return {
            "_meta": {
                "data_as_of": data_as_of or today_str,
                "insufficient_data": False,
                "record_count": len(series),
                "query_ms": elapsed_ms,
            },
            "series": series,
        }
