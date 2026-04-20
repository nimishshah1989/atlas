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
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.models.regime_v2 import CompositeRegime, RegimeBand
from backend.models.schemas import RegimeTransition
from backend.services import signal_engine

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


# ---------------------------------------------------------------------------
# RegimeComposer — S2-0 composite global + India + sector regime (slice §4.2)
# ---------------------------------------------------------------------------


_DEC = Decimal


def _band_confidence(score: Decimal) -> Decimal:
    """Confidence = clamp(|score-50|/50, 0..1) — distance from neutral midpoint."""
    delta = abs(score - _DEC("50"))
    conf = delta / _DEC("50")
    return min(max(conf, _DEC("0")), _DEC("1"))


def _global_band_from_heatmap(rows: list[dict[str, Any]]) -> RegimeBand:
    rs_vals: list[Decimal] = []
    for r in rows:
        raw = r.get("rs_composite")
        if raw is None:
            continue
        try:
            rs_vals.append(Decimal(str(raw)))
        except Exception:  # noqa: BLE001
            continue
    if not rs_vals:
        return RegimeBand(
            label="UNKNOWN",
            score=_DEC("50"),
            confidence=_DEC("0"),
            evidence=["no global RS rows"],
        )
    mean = sum(rs_vals) / Decimal(len(rs_vals))
    if mean >= _DEC("60"):
        label = "RISK_ON"
    elif mean <= _DEC("40"):
        label = "RISK_OFF"
    else:
        label = "NEUTRAL"
    return RegimeBand(
        label=label,
        score=mean.quantize(_DEC("0.01")),
        confidence=_band_confidence(mean),
        evidence=[f"global mean RS={mean:.1f} over {len(rs_vals)} instruments"],
    )


class RegimeComposer:
    """Compose global + India + sector bands into a single deployment posture."""

    def __init__(self, session: AsyncSession) -> None:
        self._svc = JIPDataService(session)

    async def compose(self) -> CompositeRegime:
        global_band = await self._global_band()
        india_band, india_data_as_of = await self._india_band()
        sectors = await self._sectors_band()

        posture = self._derive_posture(global_band, india_band)
        confidence = (global_band.confidence + india_band.confidence) / _DEC("2")

        reason = (
            f"Global={global_band.label} (s={global_band.score}), "
            f"India={india_band.label} (s={india_band.score}), posture={posture}"
        )

        return CompositeRegime(
            posture=posture,
            confidence=confidence.quantize(_DEC("0.01")),
            global_band=global_band,
            india_band=india_band,
            sectors=sectors,
            reason=reason,
            data_as_of=india_data_as_of,
        )

    async def _global_band(self) -> RegimeBand:
        try:
            rows = await self._svc.get_global_rs_heatmap()
        except Exception as exc:  # noqa: BLE001
            log.warning("regime_composer: global heatmap fetch failed", error=str(exc))
            return RegimeBand(
                label="UNKNOWN", score=_DEC("50"), confidence=_DEC("0"), evidence=["fetch failed"]
            )
        return _global_band_from_heatmap(rows or [])

    async def _india_band(self) -> tuple[RegimeBand, Optional[datetime.date]]:
        try:
            breadth = await self._svc.get_market_breadth()
        except Exception as exc:  # noqa: BLE001
            log.warning("regime_composer: breadth fetch failed", error=str(exc))
            breadth = None

        composite_breadth = _DEC("50")
        drawdown_pct = _DEC("0")
        data_as_of: Optional[datetime.date] = None
        if breadth:
            raw_b = breadth.get("breadth_score")
            if raw_b is not None:
                try:
                    composite_breadth = Decimal(str(raw_b))
                except Exception:  # noqa: BLE001
                    pass
            raw_dd = breadth.get("drawdown_pct")
            if raw_dd is not None:
                try:
                    drawdown_pct = abs(Decimal(str(raw_dd)))
                except Exception:  # noqa: BLE001
                    pass
            raw_date = breadth.get("date")
            if raw_date is not None:
                try:
                    data_as_of = datetime.date.fromisoformat(str(raw_date))
                except Exception:  # noqa: BLE001
                    data_as_of = None

        thresholds = signal_engine.load_thresholds()
        regime_sig = signal_engine.evaluate_regime(composite_breadth, drawdown_pct, thresholds)
        # Derive label from the REGIME signal reason (contains "Regime=X:")
        label = "UNKNOWN"
        if regime_sig and regime_sig.reason and "Regime=" in regime_sig.reason:
            label = regime_sig.reason.split("Regime=")[1].split(":")[0].strip()

        band = RegimeBand(
            label=label,
            score=composite_breadth.quantize(_DEC("0.01")),
            confidence=_band_confidence(composite_breadth),
            evidence=[f"breadth={composite_breadth}, drawdown={drawdown_pct}%"],
        )
        return band, data_as_of

    async def _sectors_band(self) -> list[dict[str, Any]]:
        try:
            rollups = await self._svc.get_sector_rollups()
        except Exception as exc:  # noqa: BLE001
            log.warning("regime_composer: sector rollups fetch failed", error=str(exc))
            return []
        out: list[dict[str, Any]] = []
        for r in rollups or []:
            sector = r.get("sector")
            if not sector:
                continue
            pct_above_200 = r.get("pct_above_200dma")
            try:
                breadth_val = Decimal(str(pct_above_200)) if pct_above_200 is not None else None
            except Exception:  # noqa: BLE001
                breadth_val = None
            if breadth_val is None:
                state = "UNKNOWN"
            elif breadth_val >= _DEC("60"):
                state = "GREEN"
            elif breadth_val <= _DEC("40"):
                state = "RED"
            else:
                state = "AMBER"
            out.append({"sector": sector, "breadth_state": state, "pct_above_200dma": breadth_val})
        return out

    @staticmethod
    def _derive_posture(global_band: RegimeBand, india_band: RegimeBand) -> str:
        if global_band.label == "RISK_ON" and india_band.label == "BULL":
            return "RISK_ON"
        if global_band.label == "RISK_OFF" or india_band.label == "BEAR":
            return "RISK_OFF"
        return "SELECTIVE"
