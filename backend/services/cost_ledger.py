"""Cost ledger service — tracks LLM API call costs with daily budget enforcement.

Every LLM call in ATLAS must go through this service for cost tracking
and budget awareness. The daily budget ($2.00 USD rolling 24h) is enforced
as a hard gate — calls that would exceed the budget raise BudgetExhaustedError.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasAlert, AtlasCostLedger

log = structlog.get_logger(__name__)

# Daily budget limit — rolling 24-hour window
DAILY_BUDGET_USD: Decimal = Decimal("2.00")

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


class BudgetExhaustedError(Exception):
    """Raised when an LLM call would exceed the daily budget limit.

    Callers must catch this and halt — no partial recording is performed.
    """

    def __init__(self, spent: Decimal, budget: Decimal, estimated_cost: Decimal) -> None:
        self.spent = spent
        self.budget = budget
        self.estimated_cost = estimated_cost
        super().__init__(
            f"Daily LLM budget exhausted: spent=${spent} of ${budget} budget; "
            f"estimated_cost=${estimated_cost} would exceed limit"
        )


@dataclass
class BudgetStatus:
    """Current budget status for the rolling 24-hour window.

    status: "under" | "at" | "over"
    spent: total USD spent in the last 24 hours
    remaining: USD remaining before budget is exhausted
    budget: the configured daily budget limit
    """

    status: str  # "under" | "at" | "over"
    spent: Decimal
    remaining: Decimal
    budget: Decimal


async def get_rolling_window_cost(db: AsyncSession, hours: int = 24) -> Decimal:
    """Return total cost_usd from atlas_cost_ledger in the last `hours` hours.

    Uses SQL SUM with server-side NOW() for the time boundary. COALESCE ensures
    Decimal("0") is returned when no rows exist in the window (never NULL).

    Args:
        db: Async SQLAlchemy session.
        hours: Rolling window size in hours (default 24).

    Returns:
        Total USD spent in the window as Decimal. Never None.
    """
    # Use text interval to avoid Python datetime arithmetic
    interval_expr = text(f"NOW() - INTERVAL '{hours} hours'")
    result = await db.execute(
        select(
            func.coalesce(
                func.sum(AtlasCostLedger.cost_usd),
                Decimal("0"),
            )
        ).where(
            AtlasCostLedger.created_at >= interval_expr,
            AtlasCostLedger.is_deleted.is_(False),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return Decimal("0")
    return Decimal(str(row))


async def check_budget(db: AsyncSession) -> BudgetStatus:
    """Check current budget status against the rolling 24-hour window.

    Returns BudgetStatus with status "under", "at", or "over":
    - "under": spent < DAILY_BUDGET_USD (calls can proceed)
    - "at": spent == DAILY_BUDGET_USD (next call will fail)
    - "over": spent > DAILY_BUDGET_USD (calls are blocked)

    Args:
        db: Async SQLAlchemy session.

    Returns:
        BudgetStatus dataclass with spent, remaining, budget, and status.
    """
    spent = await get_rolling_window_cost(db)
    remaining = DAILY_BUDGET_USD - spent

    if spent > DAILY_BUDGET_USD:
        status = "over"
    elif spent == DAILY_BUDGET_USD:
        status = "at"
    else:
        status = "under"

    log.info(
        "budget_check",
        spent_usd=str(spent),
        remaining_usd=str(remaining),
        budget_usd=str(DAILY_BUDGET_USD),
        status=status,
    )

    return BudgetStatus(
        status=status,
        spent=spent,
        remaining=remaining,
        budget=DAILY_BUDGET_USD,
    )


async def _write_budget_alert(
    db: AsyncSession,
    spent: Decimal,
    budget: Decimal,
    estimated_cost: Decimal,
) -> None:
    """Write a budget-exceeded alert to atlas_alerts.

    This is a best-effort side effect — failures are logged but not re-raised
    so the BudgetExhaustedError propagates cleanly to the caller.

    Args:
        db: Async SQLAlchemy session.
        spent: Total spent in the rolling window.
        budget: The configured daily budget.
        estimated_cost: The cost that would have been added.
    """
    try:
        alert = AtlasAlert(
            source="cost_ledger",
            alert_type="budget_exhausted",
            message=(
                f"Daily LLM budget exhausted: spent=${spent} of ${budget} "
                f"budget. Rejected call estimated at ${estimated_cost}."
            ),
            metadata_json={
                "spent_usd": str(spent),
                "budget_usd": str(budget),
                "estimated_cost_usd": str(estimated_cost),
                "window_hours": 24,
            },
        )
        db.add(alert)
        await db.flush()
        log.warning(
            "budget_alert_written",
            spent_usd=str(spent),
            budget_usd=str(budget),
            estimated_cost_usd=str(estimated_cost),
        )
    except Exception as exc:
        log.error(
            "budget_alert_write_failed",
            error=str(exc),
            spent_usd=str(spent),
            budget_usd=str(budget),
        )


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

    Performs a pre-call budget check before recording. If the estimated cost
    would cause the 24-hour rolling window to exceed DAILY_BUDGET_USD, raises
    BudgetExhaustedError (and writes an alert to atlas_alerts as a side effect).

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

    Raises:
        BudgetExhaustedError: If this call would exceed the daily budget.
    """
    pricing = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    cost_usd = (
        Decimal(str(prompt_tokens)) * pricing["input"]
        + Decimal(str(completion_tokens)) * pricing["output"]
    ) / Decimal("1000")

    # Pre-call budget gate — check before any DB write
    budget_status = await check_budget(db)
    if budget_status.spent + cost_usd > DAILY_BUDGET_USD:
        await _write_budget_alert(db, budget_status.spent, DAILY_BUDGET_USD, cost_usd)
        raise BudgetExhaustedError(
            spent=budget_status.spent,
            budget=DAILY_BUDGET_USD,
            estimated_cost=cost_usd,
        )

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
