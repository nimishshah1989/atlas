"""PortfolioRepo — CRUD for atlas_portfolios and related tables."""

from __future__ import annotations

import datetime
import uuid
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasPortfolio, AtlasPortfolioHolding

log = structlog.get_logger()


class PortfolioRepo:
    """Repository for portfolio tables — SELECT, INSERT, soft-delete."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Portfolio CRUD
    # ------------------------------------------------------------------

    async def create_portfolio(
        self,
        portfolio: AtlasPortfolio,
        holdings: list[AtlasPortfolioHolding] | None = None,
    ) -> AtlasPortfolio:
        """Persist a new portfolio row and its holdings."""
        self._session.add(portfolio)
        await self._session.flush()

        if holdings:
            for holding in holdings:
                holding.portfolio_id = portfolio.id
                self._session.add(holding)
            await self._session.flush()

        log.info("portfolio_created", portfolio_id=str(portfolio.id))
        return portfolio

    async def get_portfolio(self, portfolio_id: uuid.UUID) -> Optional[AtlasPortfolio]:
        """Fetch a single portfolio by ID, excluding soft-deleted."""
        stmt = (
            select(AtlasPortfolio)
            .where(AtlasPortfolio.id == portfolio_id)
            .where(AtlasPortfolio.is_deleted.is_(False))
        )
        rows = await self._session.execute(stmt)
        return rows.scalar_one_or_none()

    async def list_portfolios(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[AtlasPortfolio]:
        """List portfolios, newest first, excluding soft-deleted."""
        stmt = (
            select(AtlasPortfolio)
            .where(AtlasPortfolio.is_deleted.is_(False))
            .order_by(AtlasPortfolio.created_at.desc())
            .limit(limit)
        )
        if user_id is not None:
            stmt = stmt.where(AtlasPortfolio.user_id == user_id)
        rows = await self._session.execute(stmt)
        return list(rows.scalars().all())

    async def soft_delete_portfolio(self, portfolio_id: uuid.UUID) -> bool:
        """Soft-delete a portfolio by ID."""
        portfolio = await self.get_portfolio(portfolio_id)
        if portfolio is None:
            return False
        portfolio.is_deleted = True
        portfolio.deleted_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await self._session.flush()
        log.info("portfolio_soft_deleted", portfolio_id=str(portfolio_id))
        return True

    # ------------------------------------------------------------------
    # Holdings
    # ------------------------------------------------------------------

    async def get_holdings(self, portfolio_id: uuid.UUID) -> list[AtlasPortfolioHolding]:
        """Fetch all non-deleted holdings for a portfolio."""
        stmt = (
            select(AtlasPortfolioHolding)
            .where(AtlasPortfolioHolding.portfolio_id == portfolio_id)
            .where(AtlasPortfolioHolding.is_deleted.is_(False))
            .order_by(AtlasPortfolioHolding.created_at.asc())
        )
        rows = await self._session.execute(stmt)
        return list(rows.scalars().all())
