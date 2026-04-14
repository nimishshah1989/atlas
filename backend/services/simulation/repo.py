"""SimulationRepo — CRUD for atlas_simulations table."""

from __future__ import annotations

import datetime
import uuid
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasSimulation

log = structlog.get_logger()


class SimulationRepo:
    """Repository for atlas_simulations — SELECT, INSERT, soft-delete."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_simulation(self, sim: AtlasSimulation) -> AtlasSimulation:
        """Persist a new simulation row."""
        self._session.add(sim)
        await self._session.flush()
        log.info("simulation_saved", simulation_id=str(sim.id))
        return sim

    async def get_simulation(self, sim_id: uuid.UUID) -> Optional[AtlasSimulation]:
        """Fetch a single simulation by ID, excluding soft-deleted."""
        stmt = (
            select(AtlasSimulation)
            .where(AtlasSimulation.id == sim_id)
            .where(AtlasSimulation.is_deleted.is_(False))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_simulations(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[AtlasSimulation]:
        """List simulations, newest first, excluding soft-deleted."""
        stmt = (
            select(AtlasSimulation)
            .where(AtlasSimulation.is_deleted.is_(False))
            .order_by(AtlasSimulation.created_at.desc())
            .limit(limit)
        )
        if user_id is not None:
            stmt = stmt.where(AtlasSimulation.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def lock_for_update(self, sim_id: uuid.UUID) -> Optional[AtlasSimulation]:
        """SELECT ... FOR UPDATE to prevent concurrent auto-loop races."""
        stmt = (
            select(AtlasSimulation)
            .where(AtlasSimulation.id == sim_id)
            .where(AtlasSimulation.is_deleted.is_(False))
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def soft_delete(self, sim_id: uuid.UUID) -> bool:
        """Soft-delete a simulation."""
        sim = await self.get_simulation(sim_id)
        if sim is None:
            return False
        sim.is_deleted = True
        sim.deleted_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await self._session.flush()
        log.info("simulation_soft_deleted", simulation_id=str(sim_id))
        return True
