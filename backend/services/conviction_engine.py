"""4-factor conviction engine for ATLAS C-DER-2.

Pure computation module — no HTTP dependencies, no hardcoded data.
Reads JIP tables via AsyncSession (read-only).

Factor definitions:
  factor_returns_rs:  rs_composite > 100 (equity outperforms benchmark)
  factor_momentum_rs: roc_21 percentile rank > 60th (top momentum cohort)
  factor_sector_rs:   sector rs_composite > 100 (sector itself outperforming)
  factor_volume_rs:   cmf_20 > 0 AND mfi_14 > 50 (money flowing in, buyers dominant)

One SQL round-trip via CTE for the single-instrument path.
Percentile rank for the screener bulk path computed server-side via
PostgreSQL's percent_rank() window function — never sorted in Python.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.conviction import (
    ActionSignal,
    ConvictionLevel,
    FourFactorConviction,
    UrgencyLevel,
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Single-instrument CTE query
# ---------------------------------------------------------------------------

_FOUR_FACTOR_SQL = text("""
WITH latest_tech_date AS (
    SELECT MAX(date) AS d FROM de_equity_technical_daily
),
target_tech AS (
    SELECT roc_21, cmf_20, mfi_14, roc_5
    FROM de_equity_technical_daily
    WHERE instrument_id = :instrument_id
      AND date = (SELECT d FROM latest_tech_date)
    LIMIT 1
),
target_rs AS (
    SELECT rs_composite
    FROM de_rs_scores
    WHERE entity_type = 'equity'
      AND vs_benchmark = 'NIFTY 500'
      AND entity_id = :instrument_id_str
      AND date = (SELECT MAX(date) FROM de_rs_scores
                  WHERE entity_type = 'equity' AND vs_benchmark = 'NIFTY 500')
    LIMIT 1
),
sector_rs AS (
    SELECT rs_composite AS sector_rs_composite
    FROM de_rs_scores
    WHERE entity_type = 'sector'
      AND entity_id = :sector
      AND date = (SELECT MAX(date) FROM de_rs_scores WHERE entity_type = 'sector')
    LIMIT 1
),
roc_pct_rank AS (
    SELECT pct_rank
    FROM (
        SELECT
            instrument_id,
            percent_rank() OVER (ORDER BY roc_21 ASC NULLS FIRST) AS pct_rank
        FROM de_equity_technical_daily
        WHERE date = (SELECT d FROM latest_tech_date)
    ) ranked
    WHERE instrument_id = :instrument_id
    LIMIT 1
)
SELECT
    tt.roc_21,
    tt.cmf_20,
    tt.mfi_14,
    tt.roc_5,
    tr.rs_composite,
    sr.sector_rs_composite,
    rp.pct_rank AS roc_21_pct_rank
FROM target_tech tt
LEFT JOIN target_rs tr ON true
LEFT JOIN sector_rs sr ON true
LEFT JOIN roc_pct_rank rp ON true
""")

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _to_dec(value: Any) -> Optional[Decimal]:
    """Convert a value to Decimal, returning None if not convertible or None."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return None


def _compute_conviction_from_factors(
    factors_aligned: int,
    rs_composite: Optional[Decimal],
    roc_5: Optional[Decimal],
    roc_21: Optional[Decimal],
    regime: Optional[str],
) -> tuple[ConvictionLevel, ActionSignal, UrgencyLevel]:
    """Pure function: derive conviction level, action signal, urgency from factors.

    This function performs no I/O and produces deterministic outputs given the
    same inputs. It is tested in isolation by the unit-test suite.
    """
    # ------------------------------------------------------------------ #
    # 1. Conviction level — simple count threshold                        #
    # ------------------------------------------------------------------ #
    if factors_aligned == 4:
        conviction = ConvictionLevel.HIGH_PLUS
    elif factors_aligned == 3:
        conviction = ConvictionLevel.HIGH
    elif factors_aligned == 2:
        conviction = ConvictionLevel.MEDIUM
    elif factors_aligned == 1:
        conviction = ConvictionLevel.LOW
    else:
        conviction = ConvictionLevel.AVOID

    # ------------------------------------------------------------------ #
    # 2. Action signal — conviction × regime                              #
    # ------------------------------------------------------------------ #
    bull_regime = regime is not None and regime.upper() in ("BULL", "RECOVERY")
    if conviction in (ConvictionLevel.HIGH_PLUS, ConvictionLevel.HIGH) and bull_regime:
        action = ActionSignal.BUY
    elif conviction in (ConvictionLevel.HIGH_PLUS, ConvictionLevel.HIGH):
        action = ActionSignal.ACCUMULATE
    elif conviction == ConvictionLevel.MEDIUM:
        action = ActionSignal.WATCH
    elif (
        conviction == ConvictionLevel.LOW
        and rs_composite is not None
        and rs_composite < Decimal("100")
    ):
        action = ActionSignal.REDUCE
    else:
        action = ActionSignal.EXIT

    # ------------------------------------------------------------------ #
    # 3. Urgency level — momentum quality check                           #
    # ------------------------------------------------------------------ #
    if conviction == ConvictionLevel.HIGH_PLUS and roc_5 is not None and roc_5 > Decimal("3"):
        urgency = UrgencyLevel.IMMEDIATE
    elif (
        conviction in (ConvictionLevel.HIGH_PLUS, ConvictionLevel.HIGH)
        and roc_21 is not None
        and roc_21 > Decimal("0")
    ):
        urgency = UrgencyLevel.DEVELOPING
    else:
        urgency = UrgencyLevel.PATIENT

    return conviction, action, urgency


# ---------------------------------------------------------------------------
# Single-instrument conviction computation
# ---------------------------------------------------------------------------


async def compute_four_factor(
    instrument_id: UUID,
    sector: Optional[str],
    db: AsyncSession,
    regime: Optional[str] = None,
) -> Optional[FourFactorConviction]:
    """Compute 4-factor conviction model for a single instrument.

    Returns None when the instrument has no technical row for the latest date.
    Uses one SQL round-trip via CTE — does not issue 4 separate queries.

    Args:
        instrument_id: UUID of the equity instrument.
        sector: Sector name for sector-RS lookup (None → sector factor False).
        db: Read-only AsyncSession (JIP data — never written to).
        regime: Market regime string e.g. "BULL", "BEAR", "SIDEWAYS".

    Returns:
        FourFactorConviction model or None if no technical data available.
    """
    params: dict[str, Any] = {
        "instrument_id": instrument_id,
        "instrument_id_str": str(instrument_id),
        "sector": sector,
    }
    sql_result = await db.execute(_FOUR_FACTOR_SQL, params)
    row = sql_result.mappings().first()

    if row is None:
        log.debug("four_factor_no_tech_row", instrument_id=str(instrument_id))
        return None

    roc_21 = _to_dec(row["roc_21"])
    cmf_20 = _to_dec(row["cmf_20"])
    mfi_14 = _to_dec(row["mfi_14"])
    roc_5 = _to_dec(row["roc_5"])
    rs_composite = _to_dec(row["rs_composite"])
    sector_rs_composite = _to_dec(row["sector_rs_composite"])
    roc_21_pct_rank = _to_dec(row["roc_21_pct_rank"])

    # ------------------------------------------------------------------ #
    # Factor evaluation — None values always → factor = False            #
    # Use `is not None` not truthiness (zero is a valid financial value) #
    # ------------------------------------------------------------------ #
    factor_returns_rs = rs_composite is not None and rs_composite > Decimal("100")
    factor_momentum_rs = roc_21_pct_rank is not None and roc_21_pct_rank > Decimal("0.6")
    factor_sector_rs = sector_rs_composite is not None and sector_rs_composite > Decimal("100")
    factor_volume_rs = (
        cmf_20 is not None
        and mfi_14 is not None
        and cmf_20 > Decimal("0")
        and mfi_14 > Decimal("50")
    )
    factors_aligned = sum(
        [factor_returns_rs, factor_momentum_rs, factor_sector_rs, factor_volume_rs]
    )

    conviction, action, urgency = _compute_conviction_from_factors(
        factors_aligned=factors_aligned,
        rs_composite=rs_composite,
        roc_5=roc_5,
        roc_21=roc_21,
        regime=regime,
    )

    return FourFactorConviction(
        conviction_level=conviction,
        action_signal=action,
        urgency=urgency,
        factor_returns_rs=factor_returns_rs,
        factor_momentum_rs=factor_momentum_rs,
        factor_sector_rs=factor_sector_rs,
        factor_volume_rs=factor_volume_rs,
        factors_aligned=factors_aligned,
        rs_composite=rs_composite,
        roc_21_pct_rank=roc_21_pct_rank,
        sector_rs_composite=sector_rs_composite,
        cmf_20=cmf_20,
        mfi_14=mfi_14,
        regime=regime,
    )


# ---------------------------------------------------------------------------
# Bulk screener SQL template
# Percentile rank MUST be computed in PostgreSQL — never sorted in Python.
# Universe filter comes from a whitelist (SQL injection prevention).
# Sector filter uses a bind parameter, never string interpolation.
# ---------------------------------------------------------------------------

_SCREENER_SQL_TEMPLATE = """
WITH latest_tech_date AS (
    SELECT MAX(date) AS d FROM de_equity_technical_daily
),
latest_rs_date AS (
    SELECT MAX(date) AS d FROM de_rs_scores
    WHERE entity_type = 'equity' AND vs_benchmark = 'NIFTY 500'
),
sector_rs_latest AS (
    SELECT DISTINCT ON (entity_id) entity_id AS sector_name, rs_composite AS sector_rs
    FROM de_rs_scores
    WHERE entity_type = 'sector'
      AND date = (SELECT MAX(date) FROM de_rs_scores WHERE entity_type = 'sector')
    ORDER BY entity_id
),
ranked_tech AS (
    SELECT
        instrument_id,
        roc_21, cmf_20, mfi_14, rsi_14, above_50dma, above_200dma, macd_bullish, roc_5,
        percent_rank() OVER (ORDER BY roc_21 ASC NULLS FIRST) AS roc_21_pct_rank
    FROM (
        SELECT DISTINCT ON (instrument_id)
            instrument_id,
            roc_21, cmf_20, mfi_14, rsi_14, above_50dma, above_200dma, macd_bullish, roc_5
        FROM de_equity_technical_daily
        WHERE date = (SELECT d FROM latest_tech_date)
        ORDER BY instrument_id
    ) deduped
),
latest_rs AS (
    SELECT DISTINCT ON (entity_id) entity_id AS instrument_id_str, rs_composite
    FROM de_rs_scores
    WHERE entity_type = 'equity'
      AND vs_benchmark = 'NIFTY 500'
      AND date = (SELECT d FROM latest_rs_date)
    ORDER BY entity_id
),
latest_fundamentals AS (
    SELECT DISTINCT ON (instrument_id) instrument_id, market_cap_cr, pe_ratio
    FROM de_equity_fundamentals
    ORDER BY instrument_id
)
SELECT
    i.current_symbol AS symbol,
    i.company_name, i.sector, i.nifty_50, i.nifty_500,
    t.rsi_14, t.above_50dma, t.above_200dma, t.macd_bullish,
    t.cmf_20, t.mfi_14, t.roc_21, t.roc_5, t.roc_21_pct_rank,
    r.rs_composite,
    sr.sector_rs,
    f.market_cap_cr, f.pe_ratio
FROM de_instrument i
LEFT JOIN ranked_tech t ON t.instrument_id = i.id
LEFT JOIN latest_rs r ON r.instrument_id_str = i.id::text
LEFT JOIN sector_rs_latest sr ON sr.sector_name = i.sector
LEFT JOIN latest_fundamentals f ON f.instrument_id = i.id
WHERE i.is_active = true
  {universe_filter}
  {sector_filter}
ORDER BY r.rs_composite DESC NULLS LAST
LIMIT :limit OFFSET :offset
"""

# Whitelist of allowed universe column name injections.
# NEVER allow user-supplied strings to be interpolated into the SQL.
_UNIVERSE_SQL_FRAGMENTS: dict[str, str] = {
    "nifty50": "AND i.nifty_50 = true",
    "nifty200": "AND i.nifty_200 = true",
    "nifty500": "AND i.nifty_500 = true",
}


async def compute_screener_bulk(
    filters: dict[str, Any],
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Bulk screener fetch with conviction derivation.

    Percentile rank is computed in PostgreSQL (percent_rank() window function)
    — never sorted in Python. Post-SQL conviction/action filters apply on the
    Python side only after all rows are fetched.

    Args:
        filters: Dict with optional keys: universe, sector, conviction, action,
                 regime, limit, offset.
        db: Read-only AsyncSession.

    Returns:
        List of dicts ready to be deserialized into ScreenerRow models.
    """
    universe_filter = _UNIVERSE_SQL_FRAGMENTS.get(filters.get("universe") or "", "")
    sector_param = filters.get("sector")
    sector_filter = "AND i.sector = :sector" if sector_param is not None else ""

    sql_str = _SCREENER_SQL_TEMPLATE.format(
        universe_filter=universe_filter,
        sector_filter=sector_filter,
    )

    bind_params: dict[str, Any] = {
        "limit": filters.get("limit", 50),
        "offset": filters.get("offset", 0),
    }
    if sector_param is not None:
        bind_params["sector"] = sector_param

    sql_result = await db.execute(text(sql_str).bindparams(**bind_params))
    rows = sql_result.mappings().all()

    regime = filters.get("regime") or "SIDEWAYS"
    conviction_filter = filters.get("conviction")
    action_filter = filters.get("action")

    output: list[dict[str, Any]] = []
    for row in rows:
        rs_composite = _to_dec(row["rs_composite"])
        roc_5 = _to_dec(row["roc_5"])
        roc_21 = _to_dec(row["roc_21"])
        roc_21_pct_rank = _to_dec(row["roc_21_pct_rank"])
        cmf_20 = _to_dec(row["cmf_20"])
        mfi_14 = _to_dec(row["mfi_14"])
        sector_rs = _to_dec(row["sector_rs"])

        factor_returns_rs = rs_composite is not None and rs_composite > Decimal("100")
        factor_momentum_rs = roc_21_pct_rank is not None and roc_21_pct_rank > Decimal("0.6")
        factor_sector_rs = sector_rs is not None and sector_rs > Decimal("100")
        factor_volume_rs = (
            cmf_20 is not None
            and mfi_14 is not None
            and cmf_20 > Decimal("0")
            and mfi_14 > Decimal("50")
        )
        factors_aligned = sum(
            [factor_returns_rs, factor_momentum_rs, factor_sector_rs, factor_volume_rs]
        )

        conviction, action, urgency = _compute_conviction_from_factors(
            factors_aligned=factors_aligned,
            rs_composite=rs_composite,
            roc_5=roc_5,
            roc_21=roc_21,
            regime=regime,
        )

        # Python-side post-SQL filter — applied after conviction derivation
        if conviction_filter is not None and conviction.value != conviction_filter:
            continue
        if action_filter is not None and action.value != action_filter:
            continue

        output.append(
            {
                "symbol": row["symbol"],
                "company_name": row["company_name"],
                "sector": row["sector"],
                "rs_composite": rs_composite,
                "rsi_14": _to_dec(row["rsi_14"]),
                "above_50dma": row["above_50dma"],
                "above_200dma": row["above_200dma"],
                "macd_bullish": row["macd_bullish"],
                "market_cap_cr": _to_dec(row["market_cap_cr"]),
                "pe_ratio": _to_dec(row["pe_ratio"]),
                "conviction_level": conviction,
                "action_signal": action,
                "urgency": urgency,
                "nifty_50": bool(row["nifty_50"]),
                "nifty_500": bool(row["nifty_500"]),
            }
        )

    return output
