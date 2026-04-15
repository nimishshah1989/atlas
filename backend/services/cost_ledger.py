"""Cost ledger service — tracks LLM API call costs.

Every LLM call in ATLAS must go through this service for cost tracking
and budget awareness.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasCostLedger

log = structlog.get_logger(__name__)

# Model pricing (USD per 1K tokens)
# Haiku is the default for persona agents (cheap, fast)
MODEL_PRICING: dict[str, dict[str, Decimal]] = {
    "claude-haiku-4-5-20251001": {
        "input": Decimal("0.0008"),
        "output": Decimal("0.004"),
    },
    "claude-sonnet-4-6": {
        "input": Decimal("0.003"),
        "output": Decimal("0.015"),
    },
}

# Fallback pricing for unknown models
_DEFAULT_PRICING: dict[str, Decimal] = {
    "input": Decimal("0.001"),
    "output": Decimal("0.005"),
}


async def record_llm_call(
    db: AsyncSession,
    agent_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    request_type: str,
    metadata: dict[str, Any] | None = None,
) -> AtlasCostLedger:
    """Record an LLM API call in the cost ledger.

    Calculates cost from token counts and model pricing. All financial values
    are Decimal — never float.

    Args:
        db: Async SQLAlchemy session (must be in active transaction).
        agent_id: The agent that made the call (e.g. "persona-jhunjhunwala").
        model: Anthropic model ID (e.g. "claude-haiku-4-5-20251001").
        prompt_tokens: Input token count from API response.
        completion_tokens: Output token count from API response.
        request_type: Category of request (e.g. "persona_analysis").
        metadata: Optional extra context to store in JSONB.

    Returns:
        The persisted AtlasCostLedger row (flushed, not committed).
    """
    pricing = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    cost_usd = (
        Decimal(str(prompt_tokens)) * pricing["input"]
        + Decimal(str(completion_tokens)) * pricing["output"]
    ) / Decimal("1000")

    entry = AtlasCostLedger(
        agent_id=agent_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=cost_usd,
        request_type=request_type,
        metadata_json=metadata,
    )
    db.add(entry)
    await db.flush()

    log.info(
        "cost_ledger_recorded",
        agent_id=agent_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=str(cost_usd),
        request_type=request_type,
    )
    return entry
