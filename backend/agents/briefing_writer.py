"""Briefing Writer Agent — daily morning briefing via multi-sub-agent debate.

Spec V5-8: 4 sub-agents (macro, sentiment, technical, risk) each produce a perspective
via LLM. A bull/bear debate judge resolves conviction. An editor synthesises into a
structured morning briefing written to atlas_briefings with idempotent upsert.

Architecture:
- 4 perspective sub-agents (haiku) → bull/bear perspectives
- 1 debate judge (haiku) → conviction level
- 1 editor (sonnet) → JSON structured briefing

Public entry point: run(db, jip, data_as_of)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.db.models import AtlasIntelligence
from backend.services.intelligence import _sanitize_for_jsonb, store_finding
from backend.services.llm_client import DEFAULT_MODEL, complete

log = structlog.get_logger(__name__)

AGENT_ID = "briefing-writer"
AGENT_TYPE = "llm"
EDITOR_MODEL = "claude-sonnet-4-5-20241022"

# Conviction levels matching spec
CONVICTION_LEVELS = ("strong_bull", "bull", "neutral", "bear", "strong_bear")

# Confidence for the companion intelligence finding
CONFIDENCE_BRIEFING = Decimal("0.80")

# ---------------------------------------------------------------------------
# Sub-agent perspective prompts
# ---------------------------------------------------------------------------

_SUB_AGENT_SYSTEM: dict[str, str] = {
    "macro": (
        "You are a macro economist focused on the Indian market. "
        "You analyse macroeconomic signals: interest rates, inflation, FII/DII flows, "
        "global cues (US Fed, crude oil, dollar index), and their implication for Indian equities. "
        "Write a concise 2-3 paragraph perspective on the current macro environment."
    ),
    "sentiment": (
        "You are a market sentiment analyst for Indian equity markets. "
        "You assess investor sentiment through market breadth, VIX levels, put-call ratios, "
        "institutional activity, and media sentiment. "
        "Write a concise 2-3 paragraph perspective on current market sentiment."
    ),
    "technical": (
        "You are a technical analyst specialised in Indian equities (NSE/BSE). "
        "You analyse price action, moving averages (50/200 DMA), RSI, volume trends, "
        "support/resistance levels, and relative strength of sectors. "
        "Write a concise 2-3 paragraph perspective on the technical picture."
    ),
    "risk": (
        "You are a risk manager at an Indian equity fund. "
        "You identify key downside risks: geopolitical events, regulatory changes, "
        "earnings disappointments, sector-specific risks, and global contagion risks. "
        "Write a concise 2-3 paragraph perspective on current risk factors."
    ),
}


def _build_sub_agent_user_message(
    agent_name: str,
    upstream_findings: list[str],
    data_as_of: datetime,
) -> str:
    """Build the user message for a sub-agent perspective call."""
    findings_text = (
        "\n\n".join(upstream_findings[:5])
        if upstream_findings
        else "No upstream findings available."
    )
    return (
        f"Market briefing date: {data_as_of.strftime('%d-%b-%Y')}\n\n"
        f"Upstream intelligence findings (for context):\n{findings_text}\n\n"
        f"As the {agent_name} analyst, provide your perspective on the current market situation "
        f"for Indian equity investors. Focus on what matters most from your domain."
    )


def _build_judge_system_prompt() -> str:
    return (
        "You are an experienced portfolio manager who must adjudicate a bull vs bear debate "
        "about the Indian equity market. You will receive perspectives from 4 analysts. "
        "Your job is to weigh the arguments and determine the overall market conviction. "
        "Output ONLY one of these exact conviction levels: "
        "strong_bull, bull, neutral, bear, strong_bear. "
        "Then on the next line, write 1-2 sentences explaining your ruling."
    )


def _build_judge_user_message(perspectives: dict[str, str], data_as_of: datetime) -> str:
    """Build the debate judge user message from sub-agent perspectives."""
    persp_text = "\n\n".join(
        f"[{name.upper()} ANALYST]\n{text_}" for name, text_ in perspectives.items()
    )
    return (
        f"Date: {data_as_of.strftime('%d-%b-%Y')}\n\n"
        f"Four analyst perspectives on the Indian equity market:\n\n{persp_text}\n\n"
        "Based on these perspectives, what is your overall conviction for Indian equities? "
        "Reply with a single conviction level (strong_bull/bull/neutral/bear/strong_bear) "
        "on the first line, then your 1-2 sentence ruling."
    )


def _build_editor_system_prompt() -> str:
    return (
        "You are the chief market strategist at an Indian wealth management firm. "
        "You synthesise multiple analyst perspectives into a structured morning briefing "
        "for portfolio managers and advisors. "
        "You MUST respond with valid JSON matching this exact schema:\n"
        "{\n"
        '  "headline": "string (1 line, max 120 chars)",\n'
        '  "narrative": "string (2-4 paragraphs, plain text)",\n'
        '  "key_signals": ["signal1", "signal2", ...],\n'
        '  "theses": ["thesis1", "thesis2", ...],\n'
        '  "patterns": ["pattern1", ...],\n'
        '  "india_implication": "string (1-2 sentences)",\n'
        '  "risk_scenario": "string (1-2 sentences)"\n'
        "}\n"
        "Respond with JSON only — no markdown fences, no extra text."
    )


def _build_editor_user_message(
    perspectives: dict[str, str],
    conviction: str,
    judge_ruling: str,
    data_as_of: datetime,
) -> str:
    """Build the editor synthesis user message."""
    persp_text = "\n\n".join(f"[{name.upper()}]\n{text_}" for name, text_ in perspectives.items())
    return (
        f"Morning Briefing Date: {data_as_of.strftime('%d-%b-%Y')}\n\n"
        f"JUDGE RULING: Conviction = {conviction}\n{judge_ruling}\n\n"
        f"ANALYST PERSPECTIVES:\n{persp_text}\n\n"
        "Synthesise these into a structured morning briefing JSON as specified."
    )


# ---------------------------------------------------------------------------
# JSON parse helpers
# ---------------------------------------------------------------------------


def _parse_editor_response(raw: str) -> dict[str, Any]:
    """Parse editor LLM response as JSON. Falls back to raw text as narrative."""
    # Strip potential markdown code fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last fence lines
        cleaned = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    try:
        data = json.loads(cleaned)
        return {
            "headline": str(data.get("headline", "Indian Equity Market Morning Briefing")),
            "narrative": str(data.get("narrative", raw)),
            "key_signals": data.get("key_signals") or [],
            "theses": data.get("theses") or [],
            "patterns": data.get("patterns") or [],
            "india_implication": data.get("india_implication"),
            "risk_scenario": data.get("risk_scenario"),
        }
    except (json.JSONDecodeError, ValueError):
        log.warning("briefing_writer_json_parse_failed", raw_length=len(raw))
        return {
            "headline": "Indian Equity Market Morning Briefing",
            "narrative": raw,
            "key_signals": [],
            "theses": [],
            "patterns": [],
            "india_implication": None,
            "risk_scenario": None,
        }


def _parse_conviction(judge_response: str) -> tuple[str, str]:
    """Extract conviction level and ruling text from judge response.

    Returns (conviction, ruling_text). Falls back to 'neutral' if not parseable.
    """
    first_line = judge_response.strip().split("\n")[0].strip().lower()
    for level in sorted(CONVICTION_LEVELS, key=len, reverse=True):
        if level in first_line:
            ruling = "\n".join(judge_response.strip().split("\n")[1:]).strip()
            return level, ruling or judge_response
    # Fallback
    log.warning("briefing_writer_conviction_parse_failed", first_line=first_line)
    return "neutral", judge_response


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------


async def _upsert_briefing(
    db: AsyncSession,
    briefing_date: Any,  # datetime.date
    scope: str,
    scope_key: str | None,
    parsed: dict[str, Any],
    conviction: str,
    staleness_flags: dict[str, Any] | None,
    now: datetime,
) -> None:
    """Idempotent upsert of briefing row using raw SQL text()."""
    import json as _json

    upsert_sql = text(
        """
        INSERT INTO atlas_briefings (
            date, scope, scope_key,
            headline, narrative,
            key_signals, theses, patterns,
            india_implication, risk_scenario,
            conviction, model_used, staleness_flags,
            is_deleted, generated_at, created_at, updated_at
        ) VALUES (
            :date, :scope, :scope_key,
            :headline, :narrative,
            CAST(:key_signals AS jsonb), CAST(:theses AS jsonb), CAST(:patterns AS jsonb),
            :india_implication, :risk_scenario,
            :conviction, :model_used, CAST(:staleness_flags AS jsonb),
            false, :generated_at, :created_at, :updated_at
        )
        ON CONFLICT (date, scope, COALESCE(scope_key, '__null__'))
        DO UPDATE SET
            headline         = EXCLUDED.headline,
            narrative        = EXCLUDED.narrative,
            key_signals      = EXCLUDED.key_signals,
            theses           = EXCLUDED.theses,
            patterns         = EXCLUDED.patterns,
            india_implication = EXCLUDED.india_implication,
            risk_scenario    = EXCLUDED.risk_scenario,
            conviction       = EXCLUDED.conviction,
            model_used       = EXCLUDED.model_used,
            staleness_flags  = EXCLUDED.staleness_flags,
            generated_at     = EXCLUDED.generated_at,
            updated_at       = EXCLUDED.updated_at
        """
    )

    params = {
        "date": briefing_date,
        "scope": scope,
        "scope_key": scope_key,
        "headline": parsed["headline"],
        "narrative": parsed["narrative"],
        "key_signals": _json.dumps(parsed.get("key_signals") or []),
        "theses": _json.dumps(parsed.get("theses") or []),
        "patterns": _json.dumps(parsed.get("patterns") or []),
        "india_implication": parsed.get("india_implication"),
        "risk_scenario": parsed.get("risk_scenario"),
        "conviction": conviction,
        "model_used": EDITOR_MODEL,
        "staleness_flags": _json.dumps(staleness_flags) if staleness_flags else "null",
        "generated_at": now,
        "created_at": now,
        "updated_at": now,
    }

    await db.execute(upsert_sql, params)
    await db.commit()


# ---------------------------------------------------------------------------
# Upstream intelligence fetch
# ---------------------------------------------------------------------------


async def _fetch_upstream_findings(
    db: AsyncSession,
    data_as_of: datetime,
) -> tuple[list[str], dict[str, Any] | None]:
    """Read recent intelligence findings for context.

    Returns (list_of_content_strings, staleness_flags_or_None).
    """
    from datetime import timedelta

    min_age = data_as_of - timedelta(hours=72)
    stmt = (
        select(AtlasIntelligence)
        .where(
            AtlasIntelligence.is_deleted == False,  # noqa: E712
            AtlasIntelligence.data_as_of >= min_age,
        )
        .order_by(AtlasIntelligence.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    if not rows:
        log.warning("briefing_writer_no_upstream_findings", data_as_of=str(data_as_of))
        return [], {"upstream": "no_findings", "scope": "market"}

    contents = [f"[{r.finding_type}] {r.title}: {r.content[:500]}" for r in rows]
    log.info("briefing_writer_upstream_found", count=len(rows), data_as_of=str(data_as_of))
    return contents, None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run(
    db: AsyncSession,
    jip: JIPDataService,
    data_as_of: datetime,
    scope: str = "market",
    scope_key: str | None = None,
) -> dict[str, Any]:
    """Run the briefing writer agent.

    Args:
        db: Async SQLAlchemy session.
        jip: JIP data service (read-only, available for future enrichment).
        data_as_of: Timezone-aware datetime for the briefing.
        scope: Briefing scope, defaults to 'market'.
        scope_key: Optional sub-scope key (e.g. sector name).

    Returns:
        Summary dict with briefing metadata.
    """
    if data_as_of.tzinfo is None:
        raise ValueError("data_as_of must be timezone-aware (IST or UTC)")

    briefing_date = data_as_of.date()
    now = datetime.now(timezone.utc)
    log.info(
        "briefing_writer_start",
        agent_id=AGENT_ID,
        data_as_of=str(data_as_of),
        scope=scope,
        scope_key=scope_key,
    )

    # Step 1: Fetch upstream intelligence
    upstream_findings, staleness_flags = await _fetch_upstream_findings(db, data_as_of)

    # Step 2: 4 sub-agent perspectives
    perspectives: dict[str, str] = {}
    for agent_name, system_prompt in _SUB_AGENT_SYSTEM.items():
        response = await complete(
            db=db,
            agent_id=AGENT_ID,
            system_prompt=system_prompt,
            user_message=_build_sub_agent_user_message(agent_name, upstream_findings, data_as_of),
            model=DEFAULT_MODEL,
            request_type="briefing_perspective",
            metadata={
                "sub_agent": agent_name,
                "data_as_of": data_as_of.isoformat(),
                "scope": scope,
            },
        )
        perspectives[agent_name] = response
        log.info("briefing_writer_perspective_done", sub_agent=agent_name)

    # Step 3: Debate judge — pick conviction
    judge_response = await complete(
        db=db,
        agent_id=AGENT_ID,
        system_prompt=_build_judge_system_prompt(),
        user_message=_build_judge_user_message(perspectives, data_as_of),
        model=DEFAULT_MODEL,
        request_type="briefing_judge",
        metadata={"data_as_of": data_as_of.isoformat(), "scope": scope},
    )
    conviction, judge_ruling = _parse_conviction(judge_response)
    log.info("briefing_writer_conviction", conviction=conviction)

    # Step 4: Editor synthesis — structured JSON
    editor_response = await complete(
        db=db,
        agent_id=AGENT_ID,
        system_prompt=_build_editor_system_prompt(),
        user_message=_build_editor_user_message(perspectives, conviction, judge_ruling, data_as_of),
        model=EDITOR_MODEL,
        request_type="briefing_synthesis",
        metadata={"data_as_of": data_as_of.isoformat(), "scope": scope},
    )
    parsed = _parse_editor_response(editor_response)

    # Step 5: Upsert to atlas_briefings
    await _upsert_briefing(
        db=db,
        briefing_date=briefing_date,
        scope=scope,
        scope_key=scope_key,
        parsed=parsed,
        conviction=conviction,
        staleness_flags=staleness_flags,
        now=now,
    )

    # Step 6: Also write a companion intelligence finding for provenance
    safe_evidence = _sanitize_for_jsonb(
        {
            "conviction": conviction,
            "judge_ruling": judge_ruling,
            "sub_agents": list(perspectives.keys()),
            "upstream_findings_used": len(upstream_findings),
            "data_as_of": data_as_of.isoformat(),
            "editor_model": EDITOR_MODEL,
            "staleness_flags": staleness_flags or {},
        }
    )
    await store_finding(
        db=db,
        agent_id=AGENT_ID,
        agent_type=AGENT_TYPE,
        entity=f"market-briefing-{briefing_date.isoformat()}",
        entity_type="market",
        finding_type="morning_briefing",
        title=f"Morning Briefing — {data_as_of.strftime('%d-%b-%Y')} — {conviction}",
        content=parsed["narrative"],
        confidence=CONFIDENCE_BRIEFING,
        data_as_of=data_as_of,
        evidence=safe_evidence,
        tags=["briefing", "llm", "market", conviction],
    )

    summary = {
        "briefing_date": briefing_date.isoformat(),
        "scope": scope,
        "scope_key": scope_key,
        "conviction": conviction,
        "model_used": EDITOR_MODEL,
        "llm_calls": 6,
        "upstream_findings_used": len(upstream_findings),
        "staleness_flags": staleness_flags,
        "headline": parsed["headline"],
    }
    log.info(
        "briefing_writer_complete",
        agent_id=AGENT_ID,
        briefing_date=briefing_date.isoformat(),
        conviction=conviction,
        llm_calls=6,
    )
    return summary
