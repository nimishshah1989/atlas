"""MF Computation Service — RS momentum, quadrant classification, manager alpha passthrough.

Spec §4.1 RS Momentum:
    rs_momentum_28d = rs_composite(today) - rs_composite(28 calendar days ago)

Spec §4.2 Quadrant Classification:
    LEADING    = rs_composite > 0 AND rs_momentum > 0
    IMPROVING  = rs_composite < 0 AND rs_momentum > 0
    WEAKENING  = rs_composite > 0 AND rs_momentum < 0
    LAGGING    = rs_composite < 0 AND rs_momentum < 0

All inputs and outputs are Decimal — never float. NULL inputs produce NULL outputs.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog

from backend.clients.sql_fragments import safe_decimal
from backend.models.schemas import Quadrant

log = structlog.get_logger(__name__)

_ZERO = Decimal("0")
_MIN_LOOKBACK_DAYS = 28


def compute_rs_momentum_28d(
    rs_history: list[dict[str, Any]],
) -> Optional[Decimal]:
    """Compute RS momentum over 28 calendar days from sorted RS history.

    Args:
        rs_history: List of dicts sorted by date ASC. Each dict must have:
                    - 'date': datetime.date or ISO date string
                    - 'rs_composite': Decimal | None

    Returns:
        Decimal difference (latest_rs_composite - past_rs_composite), or
        None if there are <28 days of history or rs_composite is missing.
    """
    if not rs_history:
        return None

    # Sort defensively by date ascending to ensure correct ordering
    def _to_date(d: Any) -> datetime.date:
        if isinstance(d, datetime.date):
            return d
        return datetime.date.fromisoformat(str(d))

    sorted_history = sorted(rs_history, key=lambda r: _to_date(r["date"]))

    latest_row = sorted_history[-1]
    latest_rs = safe_decimal(latest_row.get("rs_composite"))
    if latest_rs is None:
        log.debug("mf_compute.no_latest_rs_composite")
        return None

    latest_date = _to_date(latest_row["date"])
    cutoff_date = latest_date - datetime.timedelta(days=_MIN_LOOKBACK_DAYS)

    # Find the most recent row whose date <= cutoff_date (28+ days ago)
    past_rs: Optional[Decimal] = None
    for row in reversed(sorted_history[:-1]):
        row_date = _to_date(row["date"])
        if row_date <= cutoff_date:
            past_rs = safe_decimal(row.get("rs_composite"))
            break

    if past_rs is None:
        log.debug(
            "mf_compute.insufficient_rs_history",
            latest_date=str(latest_date),
            cutoff_date=str(cutoff_date),
            history_len=len(rs_history),
        )
        return None

    return latest_rs - past_rs


def classify_fund_quadrant(
    rs_composite: Optional[Decimal],
    rs_momentum_28d: Optional[Decimal],
) -> Optional[Quadrant]:
    """Classify a fund into an RRG quadrant.

    Uses spec §4.2 strict inequality (> 0, not >= 0).
    Zero is treated as negative boundary.

    Returns None if either input is None.
    """
    if rs_composite is None or rs_momentum_28d is None:
        return None

    composite_positive = rs_composite > _ZERO
    momentum_positive = rs_momentum_28d > _ZERO

    if composite_positive and momentum_positive:
        return Quadrant.LEADING
    elif not composite_positive and momentum_positive:
        return Quadrant.IMPROVING
    elif composite_positive and not momentum_positive:
        return Quadrant.WEAKENING
    else:
        return Quadrant.LAGGING


def enrich_fund_with_computations(
    fund_row: dict[str, Any],
    rs_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Enrich a raw JIP universe row with computed fields.

    Computes rs_momentum_28d and quadrant. manager_alpha is already
    present in the JIP data (de_mf_derived_daily) — passed through unchanged.

    Args:
        fund_row: Raw dict from JIP universe query (e.g. from get_mf_universe).
                  Expected to have 'derived_rs_composite' or 'rs_composite' key.
        rs_history: RS history rows for this fund (sorted by date ASC).

    Returns:
        New dict (fund_row copy) with rs_momentum_28d and quadrant added.
    """
    enriched = dict(fund_row)

    # rs_composite may be under 'derived_rs_composite' (universe query) or 'rs_composite'
    rs_composite = safe_decimal(
        fund_row.get("derived_rs_composite") or fund_row.get("rs_composite")
    )

    rs_momentum = compute_rs_momentum_28d(rs_history)
    quadrant = classify_fund_quadrant(rs_composite, rs_momentum)

    enriched["rs_composite"] = rs_composite
    enriched["rs_momentum_28d"] = rs_momentum
    enriched["quadrant"] = quadrant

    # manager_alpha is passed through from JIP data — ensure Decimal
    enriched["manager_alpha"] = safe_decimal(fund_row.get("manager_alpha"))

    return enriched


def compute_universe_metrics(
    universe_rows: list[dict[str, Any]],
    rs_histories: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Batch enrichment: compute rs_momentum_28d and quadrant for the whole universe.

    Args:
        universe_rows: List of raw JIP universe dicts (each must have 'mstar_id').
        rs_histories: Dict mapping mstar_id -> list of RS history dicts (date ASC).

    Returns:
        List of enriched dicts. Funds with no RS history get None for momentum/quadrant.
    """
    if not universe_rows:
        return []

    before_count = len(universe_rows)
    results: list[dict[str, Any]] = []

    for row in universe_rows:
        mstar_id = row.get("mstar_id", "")
        history = rs_histories.get(mstar_id, [])
        enriched = enrich_fund_with_computations(row, history)
        results.append(enriched)

    after_count = len(results)
    log.info(
        "mf_compute.universe_enriched",
        before=before_count,
        after=after_count,
        with_momentum=sum(1 for r in results if r.get("rs_momentum_28d") is not None),
        with_quadrant=sum(1 for r in results if r.get("quadrant") is not None),
    )
    return results
