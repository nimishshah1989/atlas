"""Investor Persona Agents — 4 distinct investment philosophies powered by LLM.

Spec V5-10a: 4 personas analyse the equity universe via RS data and write
findings to atlas_intelligence with full provenance. Each LLM call is recorded
in the cost ledger via backend.services.llm_client.

Personas:
- jhunjhunwala: Indian value + momentum hybrid. Growth at reasonable price + RS
  momentum confirmation. Bullish bias, high conviction bets.
- value-investor: Deep value / Buffett-style. Quality companies below intrinsic
  value. RS is secondary to fundamentals. Patient, low turnover.
- momentum-trader: Purely technical/momentum. RS quadrant is king. LEADING = buy,
  LAGGING = avoid. Fast turnover, follows the trend.
- contrarian: Goes against consensus. Interested in LAGGING → IMPROVING transitions.
  Buys when others sell. Higher risk tolerance.

Each persona reads equity universe + RS data via JIP client, calls LLM for
analysis, writes findings tagged with its persona identifier, and includes
full provenance (persona name, source RS data, LLM model) in evidence.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.rs_analyzer import _to_decimal, classify_quadrant
from backend.clients.jip_data_service import JIPDataService
from backend.services.intelligence import store_finding
from backend.services.llm_client import DEFAULT_MODEL, complete

log = structlog.get_logger(__name__)

AGENT_TYPE = "llm"

# Finding type constants
FINDING_PERSONA_ANALYSIS = "persona_analysis"
FINDING_PERSONA_SUMMARY = "persona_summary"

# Number of top stocks to pass to LLM per persona (keep context window manageable)
_DEFAULT_TOP_N = 10

# Confidence for LLM-derived findings (lower than pure-computation — inherent uncertainty)
CONFIDENCE_FINDING = Decimal("0.70")
CONFIDENCE_SUMMARY = Decimal("0.75")

_ZERO = Decimal("0")

# ---------------------------------------------------------------------------
# Persona definitions
# ---------------------------------------------------------------------------

_PERSONAS: dict[str, dict[str, str]] = {
    "jhunjhunwala": {
        "display_name": "Rakesh Jhunjhunwala Style",
        "philosophy": (
            "You invest like Rakesh Jhunjhunwala — India's greatest investor. "
            "You look for growth at reasonable price (GARP), strong management, "
            "and large addressable markets. You take high-conviction, concentrated bets "
            "and hold for the long term. You use RS momentum as a confirmation signal: "
            "a LEADING RS quadrant confirms your conviction, while IMPROVING suggests "
            "an early entry opportunity. You are fundamentally bullish on India's growth story."
        ),
    },
    "value-investor": {
        "display_name": "Deep Value Investor",
        "philosophy": (
            "You are a disciplined value investor in the Buffett-Munger tradition. "
            "You seek high-quality businesses with durable competitive moats, "
            "trading below their intrinsic value. You are patient and have a low "
            "portfolio turnover. RS data is a secondary input — you care more about "
            "business fundamentals, but you note RS divergences as risk signals. "
            "You avoid speculative momentum plays and prefer margin of safety."
        ),
    },
    "momentum-trader": {
        "display_name": "Pure Momentum Trader",
        "philosophy": (
            "You are a disciplined momentum/trend trader. The RS quadrant is your "
            "primary signal: LEADING = strong buy, IMPROVING = potential entry, "
            "WEAKENING = reduce or exit, LAGGING = avoid or short. "
            "You follow the trend without questioning fundamentals. "
            "You have high turnover and cut losses quickly. "
            "You only buy stocks showing price strength relative to the market."
        ),
    },
    "contrarian": {
        "display_name": "Contrarian Investor",
        "philosophy": (
            "You are a contrarian investor who goes against consensus. "
            "You are most interested in stocks transitioning from LAGGING to IMPROVING — "
            "when others are selling, you look for value and mean-reversion opportunities. "
            "You have a higher risk tolerance and look for beaten-down quality names. "
            "You also watch for LEADING stocks that may be overextended and vulnerable "
            "to reversal. Your edge is buying fear and selling greed."
        ),
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_stock_data_for_prompt(stocks: list[dict[str, Any]]) -> str:
    """Format a list of stock dicts into a concise prompt string."""
    lines: list[str] = []
    for s in stocks:
        symbol = s.get("symbol", "UNKNOWN")
        rs_composite = s.get("rs_composite")
        rs_momentum = s.get("rs_momentum")
        quadrant = s.get("_quadrant", "UNKNOWN")
        sector = s.get("sector") or "Unknown"
        lines.append(
            f"- {symbol} | Sector: {sector} | RS composite: {rs_composite} "
            f"| RS momentum: {rs_momentum} | Quadrant: {quadrant}"
        )
    return "\n".join(lines) if lines else "No stocks available."


def _build_system_prompt(persona_key: str) -> str:
    """Build the system prompt for a persona."""
    persona = _PERSONAS[persona_key]
    return (
        f"You are an expert Indian equity investor with the following investment philosophy:\n\n"
        f"{persona['philosophy']}\n\n"
        "You will be given a list of NSE-listed stocks with their Relative Strength (RS) data. "
        "RS composite > 0 means the stock is outperforming the market; < 0 means underperforming. "
        "RS momentum > 0 means the RS trend is improving; < 0 means deteriorating.\n\n"
        "Quadrant definitions:\n"
        "- LEADING: RS composite > 0, RS momentum > 0 (strong and improving)\n"
        "- WEAKENING: RS composite > 0, RS momentum < 0 (strong but fading)\n"
        "- LAGGING: RS composite < 0, RS momentum < 0 (weak and worsening)\n"
        "- IMPROVING: RS composite < 0, RS momentum > 0 (weak but recovering)\n\n"
        "Based on your philosophy, provide a brief analysis (2-3 sentences per stock) "
        "identifying which stocks look most attractive or most concerning. "
        "Be specific about which quadrant matters most for your strategy. "
        "Focus on actionable insights — buy, avoid, watch, or wait."
    )


def _build_user_message(stocks: list[dict[str, Any]], data_as_of: datetime) -> str:
    """Build the user message for a persona LLM call."""
    stock_data = _format_stock_data_for_prompt(stocks)
    return (
        f"Market data as of: {data_as_of.strftime('%d-%b-%Y')}\n\n"
        f"Analyse these {len(stocks)} stocks from your investment perspective:\n\n"
        f"{stock_data}\n\n"
        "Provide your analysis focusing on the 2-3 most actionable names "
        "based on your investment philosophy."
    )


def _safe_decimal(value: Any, field_name: str) -> Decimal | None:
    """Convert a value to Decimal, logging a warning on failure."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        log.warning("persona_decimal_parse_failed", field=field_name, value=repr(value))
        return None


# ---------------------------------------------------------------------------
# Core per-persona runner
# ---------------------------------------------------------------------------

_EMPTY_RESULT: dict[str, int] = {"findings_written": 0, "stocks_analysed": 0, "llm_calls": 0}


async def _enrich_universe(
    jip: JIPDataService,
    universe: list[dict[str, Any]],
    agent_id: str,
    top_n: int,
) -> list[dict[str, Any]]:
    """Enrich top-N stocks from universe with RS data and quadrant."""
    enriched: list[dict[str, Any]] = []
    for stock in universe[:top_n]:
        symbol: str | None = stock.get("symbol")
        if not symbol:
            continue
        detail = await jip.get_stock_detail(symbol)
        if detail is None:
            log.warning("persona_missing_stock_detail", agent_id=agent_id, symbol=symbol)
            continue
        rs_composite_raw = detail.get("rs_composite")
        rs_momentum_raw = detail.get("rs_momentum")
        if rs_composite_raw is None or rs_momentum_raw is None:
            log.warning("persona_missing_rs_values", agent_id=agent_id, symbol=symbol)
            continue
        rs_composite = _to_decimal(rs_composite_raw)
        rs_momentum = _to_decimal(rs_momentum_raw)
        quadrant = classify_quadrant(rs_composite, rs_momentum)
        enriched.append(
            {
                "symbol": symbol,
                "sector": detail.get("sector") or stock.get("sector"),
                "rs_composite": str(rs_composite),
                "rs_momentum": str(rs_momentum),
                "_quadrant": quadrant.value,
            }
        )
    return enriched


async def _write_persona_finding(
    db: AsyncSession,
    agent_id: str,
    persona_key: str,
    persona: dict[str, str],
    enriched: list[dict[str, Any]],
    llm_response: str,
    data_as_of: datetime,
) -> None:
    """Write one persona finding with full provenance."""
    await store_finding(
        db=db,
        agent_id=agent_id,
        agent_type=AGENT_TYPE,
        entity=f"market-{persona_key}",
        entity_type="market",
        finding_type=FINDING_PERSONA_ANALYSIS,
        title=(
            f"{persona['display_name']} analysis — "
            f"{len(enriched)} stocks, {data_as_of.strftime('%d-%b-%Y')}"
        ),
        content=llm_response,
        confidence=CONFIDENCE_FINDING,
        data_as_of=data_as_of,
        evidence={
            "persona_name": persona_key,
            "persona_display_name": persona["display_name"],
            "stocks_analysed": len(enriched),
            "data_as_of": data_as_of.isoformat(),
            "llm_model": DEFAULT_MODEL,
            "rs_snapshot": [
                {
                    "symbol": s["symbol"],
                    "rs_composite": s["rs_composite"],
                    "rs_momentum": s["rs_momentum"],
                    "quadrant": s["_quadrant"],
                }
                for s in enriched
            ],
        },
        tags=["persona", persona_key, "llm", "equity"],
    )


async def _run_persona(
    db: AsyncSession,
    jip: JIPDataService,
    persona_key: str,
    data_as_of: datetime,
    top_n: int = _DEFAULT_TOP_N,
) -> dict[str, int]:
    """Run a single investor persona: fetch data, call LLM, write findings."""
    agent_id = f"persona-{persona_key}"
    persona = _PERSONAS[persona_key]
    log.info("persona_agent_start", agent_id=agent_id, data_as_of=str(data_as_of))

    universe: list[dict[str, Any]] = await jip.get_equity_universe()
    if not universe:
        log.warning("persona_empty_universe", agent_id=agent_id)
        return dict(_EMPTY_RESULT)

    enriched = await _enrich_universe(jip, universe, agent_id, top_n)
    if not enriched:
        log.warning("persona_no_enriched_stocks", agent_id=agent_id)
        return dict(_EMPTY_RESULT)

    llm_response = await complete(
        db=db,
        agent_id=agent_id,
        system_prompt=_build_system_prompt(persona_key),
        user_message=_build_user_message(enriched, data_as_of),
        model=DEFAULT_MODEL,
        request_type=FINDING_PERSONA_ANALYSIS,
        metadata={
            "persona_key": persona_key,
            "stocks_in_prompt": len(enriched),
            "data_as_of": data_as_of.isoformat(),
        },
    )

    await _write_persona_finding(
        db,
        agent_id,
        persona_key,
        persona,
        enriched,
        llm_response,
        data_as_of,
    )

    log.info("persona_agent_complete", agent_id=agent_id, stocks_analysed=len(enriched))
    return {"findings_written": 1, "stocks_analysed": len(enriched), "llm_calls": 1}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

ALL_PERSONAS = list(_PERSONAS.keys())


async def run(
    db: AsyncSession,
    jip: JIPDataService,
    data_as_of: datetime,
    personas: list[str] | None = None,
    top_n: int = _DEFAULT_TOP_N,
) -> dict[str, Any]:
    """Run investor persona agents.

    Args:
        db: Async SQLAlchemy session.
        jip: JIP data service (read-only).
        data_as_of: Timezone-aware datetime for the analysis.
        personas: List of persona keys to run. Defaults to all 4.
        top_n: Number of top stocks to analyse per persona.

    Returns:
        Summary dict with per-persona results and aggregate totals.
    """
    if data_as_of.tzinfo is None:
        raise ValueError("data_as_of must be timezone-aware (IST or UTC)")

    personas_to_run = personas if personas is not None else ALL_PERSONAS
    log.info(
        "investor_personas_start",
        data_as_of=str(data_as_of),
        personas=personas_to_run,
        top_n=top_n,
    )

    results: dict[str, dict[str, int]] = {}
    total_findings = 0
    total_llm_calls = 0

    for persona_key in personas_to_run:
        if persona_key not in _PERSONAS:
            log.warning("persona_unknown_key", persona_key=persona_key)
            continue
        result = await _run_persona(db, jip, persona_key, data_as_of, top_n=top_n)
        results[persona_key] = result
        total_findings += result.get("findings_written", 0)
        total_llm_calls += result.get("llm_calls", 0)

    summary = {
        "personas_run": len(results),
        "total_findings_written": total_findings,
        "total_llm_calls": total_llm_calls,
        "per_persona": results,
    }
    log.info(
        "investor_personas_complete",
        personas_run=summary["personas_run"],
        total_findings_written=total_findings,
        total_llm_calls=total_llm_calls,
    )
    return summary
