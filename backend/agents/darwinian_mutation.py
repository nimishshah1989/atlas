"""Darwinian Mutation Runner — spec §7 + §16.15.

Manages the Darwinian evolution mutation lifecycle for agents in shadow mode.
When an agent's weight drops below 0.5, this service starts a shadow-mode
mutation evaluation cycle (5 trading days). At the end of the shadow period,
it compares Sharpe (proxied by rolling_accuracy) and either merges or reverts.

This module is a pure computation service — zero LLM calls. All financial
values are Decimal, never float. Idempotent: re-running on the same
data_as_of produces the same result.

Guardrails (spec §16.15):
- Only 1 agent mutation per 5-day cycle (no simultaneous experiments)
- Shadow testing: mutated agent runs in parallel — only original output used
- 5 trading days minimum evaluation before merge/revert decision
- Maximum 3 mutations per agent per month
- Agent weights never go below 0.3 (floor enforced by DB constraint)
- If mutation degrades Sharpe → immediate revert
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.darwinian_scorer import is_trading_day
from backend.db.models import AtlasAgentMutation, AtlasAgentWeight

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Weight threshold below which a mutation is triggered
MUTATION_TRIGGER_WEIGHT = Decimal("0.5")

# Number of trading days a shadow mutation must run before evaluation
SHADOW_TRADING_DAYS = 5

# Maximum mutations per agent per calendar month
MAX_MUTATIONS_PER_MONTH = 3

# Mutation type constant for prompt-based modifications
MUTATION_TYPE_PROMPT = "prompt_modification"

_ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Advisory lock helper
# ---------------------------------------------------------------------------


async def acquire_advisory_lock(db: AsyncSession, agent_id: str) -> bool:
    """Attempt to acquire a transaction-level advisory lock for this agent.

    Uses pg_try_advisory_xact_lock (transaction-scoped) to prevent concurrent
    mutation cycles on the same agent. Returns True if lock acquired, False
    if another process holds it.

    The lock is automatically released when the enclosing transaction
    commits or rolls back — safe with connection pooling.
    """
    lock_key = f"mutation:{agent_id}"
    lock_result = await db.execute(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
        {"key": lock_key},
    )
    row = lock_result.fetchone()
    acquired: bool = bool(row[0]) if row else False
    return acquired


# ---------------------------------------------------------------------------
# Eligibility checks
# ---------------------------------------------------------------------------


async def _count_active_shadow_experiments(db: AsyncSession) -> int:
    """Count mutations currently in 'shadow' status across ALL agents.

    Guardrail: only 1 concurrent shadow experiment is allowed.
    """
    stmt = (
        select(func.count())
        .select_from(AtlasAgentMutation)
        .where(
            AtlasAgentMutation.status == "shadow",
            AtlasAgentMutation.is_deleted.is_(False),
        )
    )
    rows = await db.execute(stmt)
    count: int = rows.scalar() or 0
    return count


async def _count_mutations_this_month(db: AsyncSession, agent_id: str, ref_date: date) -> int:
    """Count mutations started for this agent in the current calendar month."""
    month_start = ref_date.replace(day=1)
    stmt = (
        select(func.count())
        .select_from(AtlasAgentMutation)
        .where(
            AtlasAgentMutation.agent_id == agent_id,
            AtlasAgentMutation.is_deleted.is_(False),
            func.date(AtlasAgentMutation.created_at) >= month_start,
        )
    )
    rows = await db.execute(stmt)
    count: int = rows.scalar() or 0
    return count


async def _get_agent_weight(db: AsyncSession, agent_id: str) -> AtlasAgentWeight | None:
    """Fetch the weight row for an agent."""
    stmt = select(AtlasAgentWeight).where(
        AtlasAgentWeight.agent_id == agent_id,
        AtlasAgentWeight.is_deleted.is_(False),
    )
    rows = await db.execute(stmt)
    return rows.scalar_one_or_none()


async def _get_active_shadow_mutation(db: AsyncSession, agent_id: str) -> AtlasAgentMutation | None:
    """Return the active shadow-mode mutation for this agent, if any."""
    stmt = (
        select(AtlasAgentMutation)
        .where(
            AtlasAgentMutation.agent_id == agent_id,
            AtlasAgentMutation.status == "shadow",
            AtlasAgentMutation.is_deleted.is_(False),
        )
        .order_by(AtlasAgentMutation.id.desc())
        .limit(1)
    )
    rows = await db.execute(stmt)
    return rows.scalar_one_or_none()


async def _get_next_version(db: AsyncSession, agent_id: str) -> int:
    """Compute the next mutation version number for this agent."""
    stmt = select(func.coalesce(func.max(AtlasAgentMutation.version), 0)).where(
        AtlasAgentMutation.agent_id == agent_id,
        AtlasAgentMutation.is_deleted.is_(False),
    )
    rows = await db.execute(stmt)
    max_version: int = rows.scalar() or 0
    return max_version + 1


async def _check_mutation_eligible(
    db: AsyncSession,
    agent_id: str,
    data_as_of: date,
    weight_row: AtlasAgentWeight,
) -> tuple[bool, str]:
    """Check if this agent is eligible for mutation.

    Returns (eligible: bool, reason: str).

    Guardrails checked (all must pass):
    1. Weight < MUTATION_TRIGGER_WEIGHT (0.5)
    2. No active shadow mutation for THIS agent
    3. Monthly mutation count < MAX_MUTATIONS_PER_MONTH (3)
    4. No other agent currently in shadow testing (only 1 at a time)
    """
    if weight_row.weight >= MUTATION_TRIGGER_WEIGHT:
        return False, f"weight {weight_row.weight} >= threshold {MUTATION_TRIGGER_WEIGHT}"

    existing = await _get_active_shadow_mutation(db, agent_id)
    if existing is not None:
        return False, f"agent already has active shadow mutation id={existing.id}"

    month_count = await _count_mutations_this_month(db, agent_id, data_as_of)
    if month_count >= MAX_MUTATIONS_PER_MONTH:
        return (
            False,
            f"monthly mutation limit reached ({month_count}/{MAX_MUTATIONS_PER_MONTH})",
        )

    active_count = await _count_active_shadow_experiments(db)
    if active_count > 0:
        return False, f"another agent is already in shadow testing ({active_count} active)"

    return True, "eligible"


# ---------------------------------------------------------------------------
# Shadow period evaluation helpers
# ---------------------------------------------------------------------------


def _count_trading_days_between(start: date, end: date) -> int:
    """Count trading days (Mon–Fri) between start (inclusive) and end (inclusive)."""
    if end < start:
        return 0
    trading = 0
    current = start
    while current <= end:
        if is_trading_day(current):
            trading += 1
        current += timedelta(days=1)
    return trading


# ---------------------------------------------------------------------------
# Core mutation lifecycle functions
# ---------------------------------------------------------------------------


async def _start_mutation(
    db: AsyncSession,
    agent_id: str,
    data_as_of: date,
    weight_row: AtlasAgentWeight,
) -> AtlasAgentMutation:
    """Create a new shadow-mode mutation record for this agent.

    The mutation records the original rolling_accuracy (as Sharpe proxy)
    and begins the 5-trading-day shadow evaluation period.
    """
    logger = log.bind(agent_id=agent_id, data_as_of=str(data_as_of))

    version = await _get_next_version(db, agent_id)
    original_sharpe = (
        Decimal(str(weight_row.rolling_accuracy))
        if weight_row.rolling_accuracy is not None
        else None
    )

    description = (
        f"Prompt modification triggered by weight {weight_row.weight} < {MUTATION_TRIGGER_WEIGHT}. "
        f"Shadow period starts {data_as_of}. Original rolling_accuracy={original_sharpe}."
    )

    mutation = AtlasAgentMutation(
        agent_id=agent_id,
        version=version,
        status="shadow",
        mutation_type=MUTATION_TYPE_PROMPT,
        description=description,
        shadow_start_date=data_as_of,
        shadow_end_date=None,
        original_sharpe=original_sharpe,
        mutated_sharpe=None,
        outcome=None,
        outcome_reason=None,
    )
    db.add(mutation)
    await db.flush()

    logger.info(
        "darwinian_mutation.shadow_started",
        version=version,
        original_sharpe=str(original_sharpe) if original_sharpe is not None else None,
        mutation_id=mutation.id,
    )
    return mutation


def _compare_sharpe(
    mutation: AtlasAgentMutation,
    weight_row: AtlasAgentWeight,
) -> str:
    """Compare current vs original Sharpe and return 'merged' or 'reverted'."""
    current_sharpe = (
        Decimal(str(weight_row.rolling_accuracy))
        if weight_row.rolling_accuracy is not None
        else None
    )
    original_sharpe = (
        Decimal(str(mutation.original_sharpe)) if mutation.original_sharpe is not None else None
    )
    mutation.mutated_sharpe = current_sharpe

    if current_sharpe is None:
        log.info("darwinian_mutation.revert_null_sharpe", agent_id=mutation.agent_id)
        return "reverted"
    if original_sharpe is None or current_sharpe >= original_sharpe:
        return "merged"
    return "reverted"


async def _evaluate_shadow(
    db: AsyncSession,
    mutation: AtlasAgentMutation,
    data_as_of: date,
    weight_row: AtlasAgentWeight,
) -> str:
    """Determine the shadow evaluation outcome.

    Returns 'merged', 'reverted', or 'pending'.
    """
    if mutation.shadow_start_date is None:
        return "pending"

    elapsed = _count_trading_days_between(mutation.shadow_start_date, data_as_of)
    if elapsed < SHADOW_TRADING_DAYS:
        log.debug(
            "darwinian_mutation.shadow_pending",
            agent_id=mutation.agent_id,
            elapsed_trading_days=elapsed,
            required=SHADOW_TRADING_DAYS,
        )
        return "pending"

    return _compare_sharpe(mutation, weight_row)


async def _merge_mutation(
    db: AsyncSession,
    mutation: AtlasAgentMutation,
    data_as_of: date,
) -> dict[str, Any]:
    """Finalise a mutation as merged — Sharpe improved or held steady."""
    mutation.status = "merged"
    mutation.outcome = "merged"
    mutation.shadow_end_date = data_as_of
    mutation.outcome_reason = (
        f"Sharpe improved or held: original={mutation.original_sharpe}, "
        f"mutated={mutation.mutated_sharpe}. Merged on {data_as_of}."
    )
    await db.flush()

    log.info(
        "darwinian_mutation.merged",
        agent_id=mutation.agent_id,
        mutation_id=mutation.id,
        version=mutation.version,
        original_sharpe=str(mutation.original_sharpe),
        mutated_sharpe=str(mutation.mutated_sharpe),
    )
    return {
        "mutation_id": mutation.id,
        "agent_id": mutation.agent_id,
        "version": mutation.version,
        "outcome": "merged",
        "original_sharpe": str(mutation.original_sharpe),
        "mutated_sharpe": str(mutation.mutated_sharpe),
    }


async def _revert_mutation(
    db: AsyncSession,
    mutation: AtlasAgentMutation,
    data_as_of: date,
) -> dict[str, Any]:
    """Finalise a mutation as reverted — Sharpe degraded or was NULL."""
    mutation.status = "reverted"
    mutation.outcome = "reverted"
    mutation.shadow_end_date = data_as_of
    mutation.outcome_reason = (
        f"Sharpe degraded: original={mutation.original_sharpe}, "
        f"mutated={mutation.mutated_sharpe}. Reverted on {data_as_of}."
    )
    await db.flush()

    log.info(
        "darwinian_mutation.reverted",
        agent_id=mutation.agent_id,
        mutation_id=mutation.id,
        version=mutation.version,
        original_sharpe=str(mutation.original_sharpe),
        mutated_sharpe=str(mutation.mutated_sharpe),
    )
    return {
        "mutation_id": mutation.id,
        "agent_id": mutation.agent_id,
        "version": mutation.version,
        "outcome": "reverted",
        "original_sharpe": str(mutation.original_sharpe),
        "mutated_sharpe": str(mutation.mutated_sharpe),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def _process_agent(
    db: AsyncSession,
    agent_id: str,
    data_as_of: date,
    evaluated: list[dict[str, Any]],
    started: list[dict[str, Any]],
) -> None:
    """Process one agent: evaluate active shadow or start new mutation."""
    if not await acquire_advisory_lock(db, agent_id):
        log.info("darwinian_mutation.lock_skipped", agent_id=agent_id)
        return

    weight_row = await _get_agent_weight(db, agent_id)
    if weight_row is None:
        return

    active = await _get_active_shadow_mutation(db, agent_id)
    if active is not None:
        decision = await _evaluate_shadow(db, active, data_as_of, weight_row)
        if decision == "merged":
            evaluated.append(await _merge_mutation(db, active, data_as_of))
        elif decision == "reverted":
            evaluated.append(await _revert_mutation(db, active, data_as_of))
        return

    eligible, reason = await _check_mutation_eligible(db, agent_id, data_as_of, weight_row)
    if not eligible:
        return

    mutation = await _start_mutation(db, agent_id, data_as_of, weight_row)
    started.append({"mutation_id": mutation.id, "agent_id": agent_id, "version": mutation.version})


async def run_mutation_cycle(
    db: AsyncSession,
    data_as_of: date,
    candidate_agent_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Execute one Darwinian mutation cycle.

    Args:
        db: SQLAlchemy AsyncSession.
        data_as_of: Reference date (typically today's trading date).
        candidate_agent_ids: Agent IDs to consider. Defaults to all scored agents.

    Returns:
        Summary dict with evaluated and started mutations.
    """
    logger = log.bind(data_as_of=str(data_as_of))

    if not is_trading_day(data_as_of):
        logger.info("darwinian_mutation.weekend_skip", weekday=data_as_of.weekday())
        return {
            "status": "skipped",
            "reason": "weekend",
            "data_as_of": str(data_as_of),
            "evaluated": [],
            "started": [],
        }

    if candidate_agent_ids is None:
        from backend.agents.darwinian_scorer import SCORED_AGENTS

        candidate_agent_ids = list(SCORED_AGENTS.keys())

    evaluated: list[dict[str, Any]] = []
    started: list[dict[str, Any]] = []

    for agent_id in candidate_agent_ids:
        await _process_agent(db, agent_id, data_as_of, evaluated, started)

    logger.info(
        "darwinian_mutation.cycle_complete",
        evaluated_count=len(evaluated),
        started_count=len(started),
    )
    return {
        "status": "ok",
        "data_as_of": str(data_as_of),
        "evaluated": evaluated,
        "started": started,
    }
