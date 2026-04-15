"""Goldilocks Analyst Agent — cross-validate Goldilocks stock ideas against RS data.

Spec §6 AGENT 4: Reads Goldilocks stock ideas via JIPDataService.get_goldilocks_stock_ideas()
(never direct de_* SQL), looks up RS quadrant per stock via JIPDataService.get_stock_detail(),
cross-validates idea direction vs RS quadrant, and writes findings to atlas_intelligence via
store_finding.

This agent does NOT call any LLM. It is pure computation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.rs_analyzer import Quadrant, _to_decimal, classify_quadrant
from backend.clients.jip_data_service import JIPDataService
from backend.services.intelligence import store_finding

log = structlog.get_logger(__name__)

AGENT_ID = "goldilocks-analyst"
AGENT_TYPE = "computation"

# Confidence scores for findings (per spec §6 AGENT 4)
CONFIDENCE_FINDING = Decimal("0.85")
CONFIDENCE_SUMMARY = Decimal("0.90")

_ZERO = Decimal("0")

# Finding types
FINDING_ALIGNMENT = "goldilocks_alignment"
FINDING_DIVERGENCE = "goldilocks_divergence"
FINDING_NEUTRAL = "goldilocks_neutral"
FINDING_SUMMARY = "goldilocks_summary"

# Which quadrants align with a BUY idea
_BULLISH_QUADRANTS = {Quadrant.LEADING}
# Which quadrants conflict with a BUY idea
_BEARISH_QUADRANTS = {Quadrant.LAGGING}
# Which quadrants are cautionary (improving potential or weakening)
_NEUTRAL_QUADRANTS = {Quadrant.IMPROVING, Quadrant.WEAKENING}


def _is_buy_action(action: str | None) -> bool:
    """Return True if the Goldilocks action is a BUY-type signal."""
    if not action:
        return False
    return action.strip().upper() in {"BUY", "STRONG BUY", "ACCUMULATE", "ADD"}


def _safe_decimal(value: Any, field_name: str) -> Decimal | None:
    """Convert a value to Decimal, logging a warning on failure. Returns None if null."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        log.warning("goldilocks_decimal_parse_failed", field=field_name, value=repr(value))
        return None


async def _write_alignment_finding(
    db: AsyncSession,
    symbol: str,
    action: str,
    quadrant: Quadrant,
    idea_row: dict[str, Any],
    stock_detail: dict[str, Any],
    data_as_of: datetime,
) -> None:
    """Write a goldilocks_alignment finding (BUY + LEADING quadrant)."""
    entry_price = _safe_decimal(idea_row.get("entry_price"), "entry_price")
    target_price = _safe_decimal(idea_row.get("target_price"), "target_price")
    stop_loss = _safe_decimal(idea_row.get("stop_loss"), "stop_loss")
    rs_composite = _safe_decimal(stock_detail.get("rs_composite"), "rs_composite")
    rs_momentum = _safe_decimal(stock_detail.get("rs_momentum"), "rs_momentum")

    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=symbol,
        entity_type="equity",
        finding_type=FINDING_ALIGNMENT,
        title=f"Goldilocks {action} {symbol} aligns with RS {quadrant.value}",
        content=(
            f"Goldilocks {action} idea for {symbol} aligns with RS {quadrant.value} quadrant. "
            f"Entry: {entry_price}, Target: {target_price}, Stop: {stop_loss}. "
            f"RS composite: {rs_composite}, RS momentum: {rs_momentum}. "
            f"Signal confidence: HIGH — both sources agree."
        ),
        confidence=CONFIDENCE_FINDING,
        data_as_of=data_as_of,
        evidence={
            "goldilocks_symbol": symbol,
            "goldilocks_action": action,
            "goldilocks_idea_date": str(idea_row.get("idea_date") or ""),
            "goldilocks_entry_price": str(entry_price) if entry_price is not None else None,
            "goldilocks_target_price": str(target_price) if target_price is not None else None,
            "goldilocks_stop_loss": str(stop_loss) if stop_loss is not None else None,
            "goldilocks_rationale": str(idea_row.get("rationale") or ""),
            "rs_quadrant": quadrant.value,
            "rs_composite": str(rs_composite) if rs_composite is not None else None,
            "rs_momentum": str(rs_momentum) if rs_momentum is not None else None,
            "alignment": "ALIGNED",
        },
        tags=["goldilocks", "alignment", symbol.lower(), quadrant.value.lower(), "buy"],
    )


async def _write_divergence_finding(
    db: AsyncSession,
    symbol: str,
    action: str,
    quadrant: Quadrant,
    idea_row: dict[str, Any],
    stock_detail: dict[str, Any],
    data_as_of: datetime,
) -> None:
    """Write a goldilocks_divergence finding (BUY + LAGGING quadrant)."""
    entry_price = _safe_decimal(idea_row.get("entry_price"), "entry_price")
    target_price = _safe_decimal(idea_row.get("target_price"), "target_price")
    stop_loss = _safe_decimal(idea_row.get("stop_loss"), "stop_loss")
    rs_composite = _safe_decimal(stock_detail.get("rs_composite"), "rs_composite")
    rs_momentum = _safe_decimal(stock_detail.get("rs_momentum"), "rs_momentum")

    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=symbol,
        entity_type="equity",
        finding_type=FINDING_DIVERGENCE,
        title=f"Goldilocks {action} {symbol} conflicts with RS {quadrant.value} — DIVERGENT SIGNAL",
        content=(
            f"Goldilocks {action} idea for {symbol} conflicts with RS {quadrant.value} quadrant. "
            f"Entry: {entry_price}, Target: {target_price}, Stop: {stop_loss}. "
            f"RS composite: {rs_composite}, RS momentum: {rs_momentum}. "
            f"DIVERGENT SIGNAL — Goldilocks is bullish but RS shows stock is lagging."
        ),
        confidence=CONFIDENCE_FINDING,
        data_as_of=data_as_of,
        evidence={
            "goldilocks_symbol": symbol,
            "goldilocks_action": action,
            "goldilocks_idea_date": str(idea_row.get("idea_date") or ""),
            "goldilocks_entry_price": str(entry_price) if entry_price is not None else None,
            "goldilocks_target_price": str(target_price) if target_price is not None else None,
            "goldilocks_stop_loss": str(stop_loss) if stop_loss is not None else None,
            "goldilocks_rationale": str(idea_row.get("rationale") or ""),
            "rs_quadrant": quadrant.value,
            "rs_composite": str(rs_composite) if rs_composite is not None else None,
            "rs_momentum": str(rs_momentum) if rs_momentum is not None else None,
            "alignment": "DIVERGENT",
        },
        tags=["goldilocks", "divergence", symbol.lower(), quadrant.value.lower(), "buy"],
    )


async def _write_neutral_finding(
    db: AsyncSession,
    symbol: str,
    action: str,
    quadrant: Quadrant,
    idea_row: dict[str, Any],
    stock_detail: dict[str, Any],
    data_as_of: datetime,
) -> None:
    """Write a goldilocks_neutral finding (BUY + IMPROVING or WEAKENING quadrant)."""
    entry_price = _safe_decimal(idea_row.get("entry_price"), "entry_price")
    target_price = _safe_decimal(idea_row.get("target_price"), "target_price")
    stop_loss = _safe_decimal(idea_row.get("stop_loss"), "stop_loss")
    rs_composite = _safe_decimal(stock_detail.get("rs_composite"), "rs_composite")
    rs_momentum = _safe_decimal(stock_detail.get("rs_momentum"), "rs_momentum")

    if quadrant == Quadrant.IMPROVING:
        note = (
            "RS is IMPROVING — stock is recovering but not yet leading. Monitor for confirmation."
        )
    else:
        note = "RS is WEAKENING — stock was leading but momentum is fading. Caution warranted."

    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=symbol,
        entity_type="equity",
        finding_type=FINDING_NEUTRAL,
        title=f"Goldilocks {action} {symbol}: RS {quadrant.value} — cautionary note",
        content=(
            f"Goldilocks {action} idea for {symbol} with RS in {quadrant.value} quadrant. "
            f"Entry: {entry_price}, Target: {target_price}, Stop: {stop_loss}. "
            f"RS composite: {rs_composite}, RS momentum: {rs_momentum}. "
            f"{note}"
        ),
        confidence=CONFIDENCE_FINDING,
        data_as_of=data_as_of,
        evidence={
            "goldilocks_symbol": symbol,
            "goldilocks_action": action,
            "goldilocks_idea_date": str(idea_row.get("idea_date") or ""),
            "goldilocks_entry_price": str(entry_price) if entry_price is not None else None,
            "goldilocks_target_price": str(target_price) if target_price is not None else None,
            "goldilocks_stop_loss": str(stop_loss) if stop_loss is not None else None,
            "goldilocks_rationale": str(idea_row.get("rationale") or ""),
            "rs_quadrant": quadrant.value,
            "rs_composite": str(rs_composite) if rs_composite is not None else None,
            "rs_momentum": str(rs_momentum) if rs_momentum is not None else None,
            "alignment": "NEUTRAL",
        },
        tags=["goldilocks", "neutral", symbol.lower(), quadrant.value.lower(), "buy"],
    )


async def _write_summary_finding(
    db: AsyncSession,
    data_as_of: datetime,
    total_ideas: int,
    analyzed: int,
    skipped: int,
    missing_tickers: int,
    alignments: int,
    divergences: int,
    neutrals: int,
    findings_written: int,
) -> None:
    """Write the run summary finding."""
    coverage_pct = (
        Decimal(str(round(analyzed / total_ideas * 100, 2))) if total_ideas > 0 else _ZERO
    )
    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity="market",
        entity_type="summary",
        finding_type=FINDING_SUMMARY,
        title=(
            f"Goldilocks analysis: {analyzed} ideas checked, "
            f"{alignments} aligned, {divergences} divergent, {neutrals} neutral"
        ),
        content=(
            f"Goldilocks analyst run complete. "
            f"Total ideas: {total_ideas}, analyzed: {analyzed}, skipped: {skipped}. "
            f"Missing RS data (tickers not found): {missing_tickers}. "
            f"Alignments (BUY+LEADING): {alignments}. "
            f"Divergences (BUY+LAGGING): {divergences}. "
            f"Neutral (BUY+IMPROVING/WEAKENING): {neutrals}. "
            f"Data as of: {data_as_of.isoformat()}."
        ),
        confidence=CONFIDENCE_SUMMARY,
        data_as_of=data_as_of,
        evidence={
            "total_ideas": total_ideas,
            "analyzed": analyzed,
            "skipped": skipped,
            "missing_tickers": missing_tickers,
            "alignments": alignments,
            "divergences": divergences,
            "neutrals": neutrals,
            "findings_written": findings_written,
            "coverage_pct": str(coverage_pct),
        },
        tags=["goldilocks", "summary"],
    )


async def _process_stock_idea(
    db: AsyncSession,
    jip: JIPDataService,
    idea_row: dict[str, Any],
    data_as_of: datetime,
) -> tuple[int, int, int, int, int]:
    """Process one Goldilocks stock idea.

    Returns:
        (findings_written, missing_ticker, alignment, divergence, neutral)
        each 0 or 1.
    """
    symbol: str | None = idea_row.get("symbol")
    if not symbol:
        log.warning("goldilocks_missing_symbol", row=idea_row)
        return 0, 0, 0, 0, 0

    action: str = str(idea_row.get("action") or "").strip()

    # Only cross-validate BUY-type actions (skip SELL/HOLD/WATCH)
    if not _is_buy_action(action):
        log.info("goldilocks_non_buy_skipped", symbol=symbol, action=action)
        return 0, 0, 0, 0, 0

    # Look up RS data via JIP client
    stock_detail = await jip.get_stock_detail(symbol)
    if stock_detail is None:
        log.warning(
            "goldilocks_missing_ticker",
            symbol=symbol,
            message="No RS data found for symbol — data gap logged",
        )
        return 0, 1, 0, 0, 0

    # Extract RS values — use _to_decimal for safe conversion
    rs_composite_raw = stock_detail.get("rs_composite")
    rs_momentum_raw = stock_detail.get("rs_momentum")

    if rs_composite_raw is None or rs_momentum_raw is None:
        log.warning("goldilocks_missing_rs_values", symbol=symbol)
        return 0, 1, 0, 0, 0

    rs_composite = _to_decimal(rs_composite_raw)
    rs_momentum = _to_decimal(rs_momentum_raw)
    quadrant = classify_quadrant(rs_composite, rs_momentum)

    if quadrant in _BULLISH_QUADRANTS:
        await _write_alignment_finding(
            db, symbol, action, quadrant, idea_row, stock_detail, data_as_of
        )
        return 1, 0, 1, 0, 0
    elif quadrant in _BEARISH_QUADRANTS:
        await _write_divergence_finding(
            db, symbol, action, quadrant, idea_row, stock_detail, data_as_of
        )
        return 1, 0, 0, 1, 0
    else:
        # IMPROVING or WEAKENING
        await _write_neutral_finding(
            db, symbol, action, quadrant, idea_row, stock_detail, data_as_of
        )
        return 1, 0, 0, 0, 1


async def _classify_ideas(
    db: AsyncSession,
    jip: JIPDataService,
    ideas: list[dict[str, Any]],
    data_as_of: datetime,
) -> dict[str, int]:
    """Iterate over Goldilocks ideas, cross-validate each against RS, and write findings."""
    analyzed = skipped = missing_tickers = 0
    alignments = divergences = neutrals = findings_written = 0

    for idea_row in ideas:
        symbol = idea_row.get("symbol")
        if not symbol:
            skipped += 1
            continue

        action = str(idea_row.get("action") or "").strip()
        if not _is_buy_action(action):
            skipped += 1
            continue

        analyzed += 1
        fw, mt, al, dv, ne = await _process_stock_idea(db, jip, idea_row, data_as_of)
        findings_written += fw
        missing_tickers += mt
        if mt:
            analyzed -= 1
            skipped += 1
        else:
            alignments += al
            divergences += dv
            neutrals += ne

    return {
        "analyzed": analyzed,
        "skipped": skipped,
        "missing_tickers": missing_tickers,
        "alignments": alignments,
        "divergences": divergences,
        "neutrals": neutrals,
        "findings_written": findings_written,
    }


async def run(
    db: AsyncSession,
    jip: JIPDataService,
    data_as_of: datetime,
) -> dict[str, int]:
    """Main entry point for the Goldilocks analyst agent.

    Reads Goldilocks stock ideas via JIP client, cross-validates against RS,
    and writes findings to atlas_intelligence.
    """
    if data_as_of.tzinfo is None:
        raise ValueError("data_as_of must be timezone-aware (IST or UTC)")

    log.info("goldilocks_analyst_start", data_as_of=str(data_as_of))
    ideas: list[dict[str, Any]] = await jip.get_goldilocks_stock_ideas()
    totals = await _classify_ideas(db, jip, ideas, data_as_of)

    await _write_summary_finding(
        db=db,
        data_as_of=data_as_of,
        total_ideas=len(ideas),
        **totals,
    )
    totals["findings_written"] += 1

    log.info("goldilocks_analyst_complete", total_ideas=len(ideas), **totals)
    return totals
