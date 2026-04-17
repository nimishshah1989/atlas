"""Regime enrichment service for ATLAS C-DER-3.

Provides three functions consumed by the /api/v1/stocks/breadth endpoint:
  - compute_days_in_regime: consecutive days in the current market regime
  - compute_regime_history: last 5 completed regime transitions (Python RLE)
  - compute_regime_enrichment: gathers both concurrently via isolated sessions

Both leaf functions accept an AsyncSession and return typed results or None/[]
on missing data. Neither raises — missing data degrades gracefully.

No new tables. Reads de_market_regime (JIP read-only).
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.schemas import RegimeTransition

if TYPE_CHECKING:
    pass  # factory type resolved at runtime via Any

log = structlog.get_logger(__name__)


async def compute_days_in_regime(db: AsyncSession) -> Optional[int]:
    """Count consecutive days in the current regime (inclusive of today).

    Uses a CTE to:
      1. Find today's regime (most recent row).
      2. Find the last date where a different regime was in effect.
      3. Count rows with today's regime after that breakpoint.

    Returns None when de_market_regime has no rows.

    SQL uses CAST() not ::type to avoid SQLAlchemy param-cast collision.
    """
    sql = text(
        """
        WITH regime_today AS (
            SELECT regime FROM de_market_regime
            ORDER BY date DESC
            LIMIT 1
        ),
        first_break AS (
            SELECT date AS break_date FROM de_market_regime
            WHERE regime != (SELECT regime FROM regime_today)
            ORDER BY date DESC
            LIMIT 1
        )
        SELECT COUNT(*) AS days_in_regime
        FROM de_market_regime
        WHERE regime = (SELECT regime FROM regime_today)
          AND date > COALESCE(
              (SELECT break_date FROM first_break),
              CAST('2000-01-01' AS date)
          )
        """
    )

    try:
        db_result = await db.execute(sql)
        row = db_result.mappings().one_or_none()
        if row is None:
            log.info("compute_days_in_regime: no rows in de_market_regime")
            return None

        count = row["days_in_regime"]
        if count is None or int(count) == 0:
            # Table might be empty; the CTE returns 0 for empty table
            # Verify by checking total row count
            check = await db.execute(text("SELECT COUNT(*) AS c FROM de_market_regime"))
            check_row = check.mappings().one()
            if int(check_row["c"]) == 0:
                return None
        days: int = int(count)
        log.debug("compute_days_in_regime", days=days)
        return days

    except Exception as exc:
        log.warning("compute_days_in_regime failed", error=str(exc))
        return None


async def compute_regime_history(db: AsyncSession) -> list[RegimeTransition]:
    """Return the last 5 completed regime transitions via Python RLE.

    Algorithm:
      1. Fetch 400 most-recent rows from de_market_regime (ordered DESC).
      2. Walk through rows, detecting regime changes.
      3. Each detected boundary creates a RegimeTransition with:
           - started_date  = boundary_row["date"] + 1 day
           - ended_date    = previous segment end
           - duration_days = (ended_date - started_date).days + 1
      4. The first transition in the list represents the *current* open
         segment (no ended_date); skip it.
      5. Return the next 5 completed transitions (indices 1..5).

    Returns [] when table is empty or only one regime exists in the window.
    """
    sql = text(
        """
        SELECT date, regime
        FROM de_market_regime
        ORDER BY date DESC
        LIMIT 400
        """
    )

    try:
        db_result = await db.execute(sql)
        rows = db_result.mappings().all()
    except Exception as exc:
        log.warning("compute_regime_history: query failed", error=str(exc))
        return []

    if not rows:
        log.info("compute_regime_history: empty de_market_regime")
        return []

    transitions: list[RegimeTransition] = []
    current_regime: str = rows[0]["regime"]
    current_end: datetime.date = rows[0]["date"]

    for row in rows[1:]:
        row_regime: str = row["regime"]
        row_date: datetime.date = row["date"]

        if row_regime != current_regime:
            # row is the last day of the PREVIOUS regime in descending order.
            # The segment we're closing started one day after row_date.
            started_date = row_date + datetime.timedelta(days=1)
            duration = (current_end - started_date).days + 1
            transitions.append(
                RegimeTransition(
                    regime=current_regime,
                    started_date=started_date,
                    ended_date=current_end,
                    duration_days=max(duration, 1),
                    breadth_pct_at_start=None,
                )
            )
            # Move the cursor to the next (older) segment
            current_regime = row_regime
            current_end = row_date

    # transitions[0] is the current open segment (most recent) — skip it.
    # transitions[1..5] are the 5 most recently completed regimes.
    completed = transitions[1:6]
    log.debug(
        "compute_regime_history",
        transitions_found=len(transitions),
        completed_returned=len(completed),
    )
    return completed


async def compute_regime_enrichment(
    factory: Any,
) -> tuple[Optional[int], list[Any]]:
    """Gather days_in_regime and regime_history concurrently via isolated sessions.

    Accepts the async_session_factory callable so callers do not need nested
    async def wrappers. Returns (days_val, history_val) — both degrade to
    (None, []) on any error.
    """

    async def _days() -> Optional[int]:
        async with factory() as s:
            return await compute_days_in_regime(s)

    async def _history() -> list[Any]:
        async with factory() as s:
            return await compute_regime_history(s)

    days_result, history_result = await asyncio.gather(_days(), _history(), return_exceptions=True)
    days_val: Optional[int] = days_result if isinstance(days_result, int) else None
    history_val: list[Any] = history_result if isinstance(history_result, list) else []
    return days_val, history_val
