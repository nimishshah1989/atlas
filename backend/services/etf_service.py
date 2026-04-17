"""
ETF universe service.

Data path:
  1. In-process 5-min TTL cache (keyed by country|benchmark|sorted_includes|as_of)
  2. JIP DE tables via jip_helpers (DISTINCT ON wrapped)
  3. Gold RS enrichment from atlas_gold_rs_cache (DB) if include=gold_rs

Never writes to de_* tables. Reads atlas_gold_rs_cache for Gold RS enrichment.

Note: All DB fetches use sequential await (not asyncio.gather) because
SQLAlchemy async sessions do not support concurrent multiplex on a single
connection.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any, Optional
import datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.etf import (
    ETFGoldRSBlock,
    ETFRSBlock,
    ETFTechnicals,
    ETFUniverseRow,
)
from backend.models.schemas import Quadrant
from backend.services.jip_helpers import (
    etf_master_rows,
    latest_etf_rs,
    latest_etf_technicals,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# In-process TTL cache -- 5 minutes per (country, benchmark, includes_key, as_of)
# ---------------------------------------------------------------------------

_ETF_UNIVERSE_TTL = 300  # seconds
_etf_universe_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_etf_universe_locks: dict[str, asyncio.Lock] = {}

VALID_INCLUDES = frozenset({"rs", "technicals", "gold_rs"})


def _safe_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        from decimal import DecimalException, InvalidOperation

        parsed = Decimal(str(value))
        return parsed if parsed.is_finite() else None
    except (DecimalException, InvalidOperation, ValueError, ArithmeticError):
        return None


def _parse_includes(include_str: Optional[str]) -> frozenset[str]:
    if not include_str:
        return frozenset()
    parts = {part.strip().lower() for part in include_str.split(",") if part.strip()}
    invalid = parts - VALID_INCLUDES
    if invalid:
        raise ValueError(f"INVALID_INCLUDE:{','.join(sorted(invalid))}")
    return frozenset(parts)


async def _fetch_gold_rs_bulk(
    session: AsyncSession, tickers: list[str], as_of: datetime.date
) -> dict[str, dict[str, Any]]:
    """Fetch Gold RS from atlas_gold_rs_cache for a list of ETF tickers."""
    if not tickers:
        return {}
    sql = text("""
        SELECT DISTINCT ON (entity_id)
            entity_id,
            rs_vs_gold_1m,
            rs_vs_gold_3m,
            rs_vs_gold_6m,
            rs_vs_gold_12m,
            gold_rs_signal,
            gold_series,
            computed_at
        FROM atlas_gold_rs_cache
        WHERE entity_type = 'etf'
          AND entity_id = ANY(:tickers)
          AND date <= :as_of
        ORDER BY entity_id, date DESC
    """)
    await session.execute(text("SET LOCAL statement_timeout = '5000'"))
    query_result = await session.execute(sql, {"tickers": tickers, "as_of": as_of})
    rows = query_result.mappings().all()
    return {row["entity_id"]: dict(row) for row in rows}


def _build_gold_rs_block(row: dict[str, Any]) -> ETFGoldRSBlock:
    return ETFGoldRSBlock(
        rs_1m=_safe_decimal(row.get("rs_vs_gold_1m")),
        rs_3m=_safe_decimal(row.get("rs_vs_gold_3m")),
        rs_6m=_safe_decimal(row.get("rs_vs_gold_6m")),
        rs_12m=_safe_decimal(row.get("rs_vs_gold_12m")),
        signal=row.get("gold_rs_signal", "STALE"),
        gold_series=row.get("gold_series", "LBMA_USD"),
        computed_at=row.get("computed_at"),
        data_gap=(row.get("rs_vs_gold_3m") is None),
    )


def _build_rs_block(row: dict[str, Any]) -> ETFRSBlock:
    quadrant_val = row.get("quadrant")
    quadrant = None
    if quadrant_val:
        try:
            quadrant = Quadrant(str(quadrant_val).upper())
        except ValueError:
            pass
    return ETFRSBlock(
        rs_composite=_safe_decimal(row.get("rs_composite")),
        rs_momentum=_safe_decimal(row.get("rs_momentum")),
        quadrant=quadrant,
    )


def _build_technicals_block(row: dict[str, Any]) -> ETFTechnicals:
    return ETFTechnicals(
        date=row.get("date"),
        close_price=_safe_decimal(row.get("close_price")),
        volume=_safe_decimal(row.get("volume")),
        rsi_14=_safe_decimal(row.get("rsi_14")),
        macd=_safe_decimal(row.get("macd")),
        macd_signal=_safe_decimal(row.get("macd_signal")),
        macd_hist=_safe_decimal(row.get("macd_hist")),
        bb_upper=_safe_decimal(row.get("bb_upper")),
        bb_middle=_safe_decimal(row.get("bb_middle")),
        bb_lower=_safe_decimal(row.get("bb_lower")),
        bb_width=_safe_decimal(row.get("bb_width")),
        sma_20=_safe_decimal(row.get("sma_20")),
        sma_50=_safe_decimal(row.get("sma_50")),
        sma_200=_safe_decimal(row.get("sma_200")),
        ema_9=_safe_decimal(row.get("ema_9")),
        ema_21=_safe_decimal(row.get("ema_21")),
        adx_14=_safe_decimal(row.get("adx_14")),
        di_plus=_safe_decimal(row.get("di_plus")),
        di_minus=_safe_decimal(row.get("di_minus")),
        stoch_k=_safe_decimal(row.get("stoch_k")),
        stoch_d=_safe_decimal(row.get("stoch_d")),
        atr_14=_safe_decimal(row.get("atr_14")),
        obv=_safe_decimal(row.get("obv")),
        vwap=_safe_decimal(row.get("vwap")),
        mom_10=_safe_decimal(row.get("mom_10")),
        roc_10=_safe_decimal(row.get("roc_10")),
        cci_20=_safe_decimal(row.get("cci_20")),
        wpr_14=_safe_decimal(row.get("wpr_14")),
        cmf_20=_safe_decimal(row.get("cmf_20")),
    )


async def get_etf_universe(
    session: AsyncSession,
    country: Optional[str] = None,
    benchmark: Optional[str] = None,
    includes: frozenset[str] = frozenset(),
    as_of: Optional[datetime.date] = None,
) -> tuple[list[ETFUniverseRow], bool]:
    """
    Fetch ETF universe rows with optional include modules.

    Returns:
        (rows, cache_hit) tuple.
        cache_hit=True when served from in-process TTL cache.
    """
    if as_of is None:
        as_of = datetime.date.today()

    includes_key = "|".join(sorted(includes))
    cache_key = f"{country or ''}|{benchmark or ''}|{includes_key}|{as_of.isoformat()}"
    now = time.monotonic()

    # Check in-process cache
    cached = _etf_universe_cache.get(cache_key)
    if cached and now - cached[0] < _ETF_UNIVERSE_TTL:
        log.info("etf_universe_cache_hit", key=cache_key, count=len(cached[1]))
        rows = [ETFUniverseRow(**cached_row) for cached_row in cached[1]]
        return rows, True

    lock = _etf_universe_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        # Double-check after acquiring lock
        cached = _etf_universe_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < _ETF_UNIVERSE_TTL:
            rows = [ETFUniverseRow(**cached_row) for cached_row in cached[1]]
            return rows, True

        t0 = time.perf_counter()

        # Fetch master rows
        masters = await etf_master_rows(session, country=country, benchmark=benchmark)
        tickers = [master["ticker"] for master in masters]

        if not masters:
            return [], False

        # Sequential fetches -- SQLAlchemy async sessions do not support
        # concurrent multiplex; asyncio.gather on a shared session is unsafe.
        tech_rows: dict[str, dict[str, Any]] = {}
        rs_rows: dict[str, dict[str, Any]] = {}
        gold_rs_rows: dict[str, dict[str, Any]] = {}

        if "technicals" in includes:
            tech_rows = await latest_etf_technicals(session, tickers=tickers, as_of=as_of)
        if "rs" in includes:
            rs_rows = await latest_etf_rs(session, tickers=tickers, as_of=as_of)
        if "gold_rs" in includes:
            gold_rs_rows = await _fetch_gold_rs_bulk(session, tickers=tickers, as_of=as_of)

        # Assemble rows
        result_rows: list[ETFUniverseRow] = []
        for master in masters:
            ticker = master["ticker"]
            tech_data = tech_rows.get(ticker, {})

            etf_row = ETFUniverseRow(
                ticker=ticker,
                name=master.get("name", ""),
                country=master.get("country", ""),
                currency=master.get("currency", "USD"),
                sector=master.get("sector"),
                category=master.get("category"),
                benchmark=master.get("benchmark"),
                expense_ratio=_safe_decimal(master.get("expense_ratio")),
                inception_date=master.get("inception_date"),
                is_active=bool(master.get("is_active", True)),
                last_price=_safe_decimal(tech_data.get("close_price")),
                last_date=tech_data.get("date"),
                rs=(
                    _build_rs_block(rs_rows[ticker])
                    if "rs" in includes and ticker in rs_rows
                    else None
                ),
                technicals=(
                    _build_technicals_block(tech_data)
                    if "technicals" in includes and tech_data
                    else None
                ),
                gold_rs=(
                    _build_gold_rs_block(gold_rs_rows[ticker])
                    if "gold_rs" in includes and ticker in gold_rs_rows
                    else None
                ),
            )
            result_rows.append(etf_row)

        elapsed = (time.perf_counter() - t0) * 1000
        log.info("etf_universe_assembled", count=len(result_rows), elapsed_ms=round(elapsed, 1))

        # Serialize for cache (store as plain dicts to avoid Pydantic obj retention)
        serializable = [etf_row.model_dump(mode="json") for etf_row in result_rows]
        _etf_universe_cache[cache_key] = (time.monotonic(), serializable)

        return result_rows, False
