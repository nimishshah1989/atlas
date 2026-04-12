"""JIP Query Service — UQL equity query engine."""

import time
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.sql_fragments import (
    CAP_CTE,
    LATEST_DATES_CTE,
    RS_28D_CTE,
    RS_CTE,
)

log = structlog.get_logger()

FIELD_MAP = {
    "symbol": "i.current_symbol",
    "company_name": "i.company_name",
    "sector": "i.sector",
    "nifty_50": "i.nifty_50",
    "nifty_200": "i.nifty_200",
    "nifty_500": "i.nifty_500",
    "close": "t.close_adj",
    "rs_composite": "r.rs_composite",
    "rs_momentum": "(r.rs_composite - COALESCE(r28.rs_composite_28d, r.rs_composite))",
    "rsi_14": "t.rsi_14",
    "adx_14": "t.adx_14",
    "above_200dma": "t.above_200dma",
    "above_50dma": "t.above_50dma",
    "macd_histogram": "t.macd_histogram",
    "beta_nifty": "t.beta_nifty",
    "sharpe_1y": "t.sharpe_1y",
    "volatility_20d": "t.volatility_20d",
    "cap_category": "cap.cap_category",
    "quadrant": """CASE
        WHEN r.rs_composite > 0 AND (r.rs_composite - COALESCE(r28.rs_composite_28d, r.rs_composite)) > 0 THEN 'LEADING'
        WHEN r.rs_composite < 0 AND (r.rs_composite - COALESCE(r28.rs_composite_28d, r.rs_composite)) > 0 THEN 'IMPROVING'
        WHEN r.rs_composite > 0 AND (r.rs_composite - COALESCE(r28.rs_composite_28d, r.rs_composite)) < 0 THEN 'WEAKENING'
        ELSE 'LAGGING'
    END""",
}

_OPERATOR_TEMPLATES = {
    "=": "{field} = :{param}",
    "!=": "{field} != :{param}",
    ">": "{field} > :{param}",
    ">=": "{field} >= :{param}",
    "<": "{field} < :{param}",
    "<=": "{field} <= :{param}",
    "in": "{field} = ANY(:{param})",
    "contains": "{field} ILIKE :{param}",
    "is_null": "{field} IS NULL",
    "is_not_null": "{field} IS NOT NULL",
}


def _build_filter_conditions(
    filters: list[dict],
) -> tuple[list[str], dict[str, Any]]:
    """Build WHERE conditions and params from UQL filters."""
    conditions = ["i.is_active = true"]
    params: dict[str, Any] = {}

    for idx, filter_spec in enumerate(filters):
        field_sql = FIELD_MAP.get(filter_spec["field"])
        if not field_sql:
            continue
        param_key = f"p{idx}"
        operator = filter_spec["op"]

        template = _OPERATOR_TEMPLATES.get(operator)
        if template is None:
            continue

        if operator in ("is_null", "is_not_null"):
            conditions.append(template.format(field=field_sql))
        elif operator == "contains":
            conditions.append(template.format(field=field_sql, param=param_key))
            params[param_key] = f"%{filter_spec['value']}%"
        else:
            conditions.append(template.format(field=field_sql, param=param_key))
            params[param_key] = filter_spec["value"]

    return conditions, params


def _build_order_clause(sort_specs: list[dict]) -> str:
    """Build ORDER BY clause from UQL sort specs."""
    order_parts = []
    for sort_spec in sort_specs:
        field_sql = FIELD_MAP.get(sort_spec["field"])
        if field_sql:
            direction = (
                "DESC" if sort_spec.get("direction", "desc") == "desc" else "ASC"
            )
            order_parts.append(f"{field_sql} {direction} NULLS LAST")
    return ", ".join(order_parts) if order_parts else "r.rs_composite DESC NULLS LAST"


def _build_select_clause(fields: Optional[list[str]]) -> str:
    """Build SELECT clause from requested fields."""
    if fields:
        select_parts = []
        for field_name in fields:
            sql_expr = FIELD_MAP.get(field_name)
            if sql_expr:
                select_parts.append(f"{sql_expr} AS {field_name}")
        return ", ".join(select_parts) if select_parts else "i.current_symbol AS symbol"
    return """
        i.id, i.current_symbol AS symbol, i.company_name, i.sector,
        i.nifty_50, i.nifty_200, i.nifty_500,
        t.close_adj AS close, t.rsi_14, t.adx_14,
        t.above_200dma, t.above_50dma, t.macd_histogram,
        r.rs_composite,
        (r.rs_composite - COALESCE(r28.rs_composite_28d, r.rs_composite)) AS rs_momentum
    """


class JIPQueryService:
    """UQL query engine for equity data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def query_equity(
        self,
        filters: list[dict],
        sort_specs: list[dict],
        limit: int = 50,
        offset: int = 0,
        fields: Optional[list[str]] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Execute a UQL query against equity data."""
        start_time = time.monotonic()

        conditions, params = _build_filter_conditions(filters)
        where_clause = " AND ".join(conditions)
        order_clause = _build_order_clause(sort_specs)
        select_clause = _build_select_clause(fields)

        base_ctes = f"""
            WITH {LATEST_DATES_CTE},
            {RS_CTE},
            {RS_28D_CTE},
            latest_tech AS (
                SELECT instrument_id, close_adj, rsi_14, adx_14, above_200dma, above_50dma,
                       macd_histogram, beta_nifty, sharpe_1y, volatility_20d
                FROM de_equity_technical_daily
                WHERE date = (SELECT tech_date FROM latest_dates)
            ),
            {CAP_CTE}
        """

        count_sql = text(f"""
            {base_ctes}
            SELECT COUNT(*) FROM de_instrument i
            LEFT JOIN latest_rs r ON r.entity_id = i.id::text
            LEFT JOIN rs_28d r28 ON r28.entity_id = i.id::text
            LEFT JOIN latest_tech t ON t.instrument_id = i.id
            LEFT JOIN latest_cap cap ON cap.instrument_id = i.id
            WHERE {where_clause}
        """)

        count_result = await self.session.execute(count_sql, params)
        total = count_result.scalar() or 0

        data_sql = text(f"""
            {base_ctes}
            SELECT {select_clause}
            FROM de_instrument i
            LEFT JOIN latest_rs r ON r.entity_id = i.id::text
            LEFT JOIN rs_28d r28 ON r28.entity_id = i.id::text
            LEFT JOIN latest_tech t ON t.instrument_id = i.id
            LEFT JOIN latest_cap cap ON cap.instrument_id = i.id
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT :query_limit OFFSET :query_offset
        """)
        params["query_limit"] = limit
        params["query_offset"] = offset

        query_result = await self.session.execute(data_sql, params)
        rows = [dict(row) for row in query_result.mappings().all()]

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        log.info("uql_query_executed", total=total, returned=len(rows), ms=elapsed_ms)
        return rows, total
