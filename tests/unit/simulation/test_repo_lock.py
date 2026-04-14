"""Tests that SimulationRepo.lock_for_update uses SELECT ... FOR UPDATE.

Verifies the FOR UPDATE clause is present in the generated SQL, preventing
concurrent auto-loop re-runs from racing on the same simulation row.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.simulation.repo import SimulationRepo


@pytest.mark.asyncio
async def test_lock_for_update_uses_for_update_clause() -> None:
    """lock_for_update must emit FOR UPDATE in SQL."""
    captured: list = []
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=lambda stmt: captured.append(stmt) or mock_result)

    repo = SimulationRepo(mock_session)
    await repo.lock_for_update(uuid.uuid4())

    assert len(captured) == 1
    from sqlalchemy.dialects import postgresql

    sql = str(captured[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql, f"Expected FOR UPDATE, got:\n{sql}"


@pytest.mark.asyncio
async def test_lock_for_update_filters_soft_deleted() -> None:
    """lock_for_update must exclude soft-deleted rows."""
    captured: list = []
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=lambda stmt: captured.append(stmt) or mock_result)

    repo = SimulationRepo(mock_session)
    await repo.lock_for_update(uuid.uuid4())

    from sqlalchemy.dialects import postgresql

    sql = str(captured[0].compile(dialect=postgresql.dialect())).lower()
    assert "is_deleted" in sql, f"Must filter is_deleted:\n{sql}"


@pytest.mark.asyncio
async def test_get_simulation_filters_soft_deleted() -> None:
    """get_simulation must exclude soft-deleted rows."""
    captured: list = []
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=lambda stmt: captured.append(stmt) or mock_result)

    repo = SimulationRepo(mock_session)
    await repo.get_simulation(uuid.uuid4())

    from sqlalchemy.dialects import postgresql

    sql = str(captured[0].compile(dialect=postgresql.dialect())).lower()
    assert "is_deleted" in sql, f"Must filter is_deleted:\n{sql}"


@pytest.mark.asyncio
async def test_list_simulations_orders_newest_first() -> None:
    """list_simulations must order by created_at DESC."""
    captured: list = []
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=lambda stmt: captured.append(stmt) or mock_result)

    repo = SimulationRepo(mock_session)
    await repo.list_simulations(user_id="user123")

    from sqlalchemy.dialects import postgresql

    sql = str(captured[0].compile(dialect=postgresql.dialect())).lower()
    assert "created_at" in sql and "desc" in sql, f"Bad order:\n{sql}"


@pytest.mark.asyncio
async def test_list_simulations_filters_by_user_id() -> None:
    """list_simulations with user_id filters to that user."""
    captured: list = []
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=lambda stmt: captured.append(stmt) or mock_result)

    repo = SimulationRepo(mock_session)
    await repo.list_simulations(user_id="alice")

    from sqlalchemy.dialects import postgresql

    sql = str(captured[0].compile(dialect=postgresql.dialect())).lower()
    assert "user_id" in sql, f"Must filter user_id:\n{sql}"
