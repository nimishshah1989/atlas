"""BookService — portfolio holdings, watchlist, action queue, performance.

Reads from AtlasPortfolioHolding and AtlasWatchlist ORM models.
All financial values are Decimal. LensService called best-effort per holding.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasPortfolioHolding, AtlasWatchlist
from backend.services.lens_service import LensService

log = structlog.get_logger(__name__)

_D = Decimal
_ACTION_PRECEDENCE = {"SELL": 0, "AVOID": 1, "WATCH": 2}


class BookService:
    """Aggregate portfolio book data with best-effort lens enrichment."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._lens = LensService(session)

    async def holdings(self, portfolio_id: Optional[uuid.UUID] = None) -> list[dict[str, Any]]:
        """Return all non-deleted holdings, optionally filtered by portfolio_id.

        Each holding is enriched with a lens_summary via LensService (best-effort).
        """
        stmt = select(AtlasPortfolioHolding).where(
            AtlasPortfolioHolding.is_deleted == False  # noqa: E712
        )
        if portfolio_id is not None:
            stmt = stmt.where(AtlasPortfolioHolding.portfolio_id == portfolio_id)

        query_out = await self._session.execute(stmt)
        rows = query_out.scalars().all()

        out: list[dict[str, Any]] = []
        for row in rows:
            lens_summary = None
            composite_action = "HOLD"
            if row.mstar_id:
                try:
                    bundle = await self._lens.get_lenses(
                        scope="mf",
                        entity_id=row.mstar_id,
                    )
                    lens_summary = {
                        k: {
                            "value": str(lv.value) if lv.value is not None else None,
                            "signals": [s.model_dump() for s in lv.signals],
                        }
                        for k, lv in bundle.lenses.items()
                    }
                    composite_action = bundle.composite_action
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "book_service: lens fetch failed",
                        mstar_id=row.mstar_id,
                        error=str(exc),
                    )

            out.append(
                {
                    "holding_id": str(row.id),
                    "portfolio_id": str(row.portfolio_id),
                    "mstar_id": row.mstar_id,
                    "scheme_name": row.scheme_name,
                    "units": row.units,
                    "nav": row.nav,
                    "current_value": row.current_value,
                    "cost_value": row.cost_value,
                    "lens_summary": lens_summary,
                    "composite_action": composite_action,
                }
            )
        return out

    async def watchlist(self) -> list[dict[str, Any]]:
        """Return all non-deleted watchlist rows, enriched with stock lens best-effort."""
        stmt = select(AtlasWatchlist).where(
            AtlasWatchlist.is_deleted == False  # noqa: E712
        )
        query_out = await self._session.execute(stmt)
        rows = query_out.scalars().all()

        out: list[dict[str, Any]] = []
        for row in rows:
            symbols: list[str] = row.symbols or []
            for symbol in symbols:
                lens_summary = None
                composite_action = "HOLD"
                try:
                    bundle = await self._lens.get_lenses(scope="stock", entity_id=symbol)
                    lens_summary = {
                        k: {
                            "value": str(lv.value) if lv.value is not None else None,
                        }
                        for k, lv in bundle.lenses.items()
                    }
                    composite_action = bundle.composite_action
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "book_service: watchlist lens failed", symbol=symbol, error=str(exc)
                    )

                out.append(
                    {
                        "watchlist_id": str(row.id),
                        "watchlist_name": row.name,
                        "symbol": symbol,
                        "lens_summary": lens_summary,
                        "composite_action": composite_action,
                    }
                )
        return out

    async def action_queue(self, portfolio_id: Optional[uuid.UUID] = None) -> list[dict[str, Any]]:
        """Return holdings with composite_action in {SELL, AVOID, WATCH}, sorted by precedence."""
        all_holdings = await self.holdings(portfolio_id=portfolio_id)
        actionable = [h for h in all_holdings if h["composite_action"] in _ACTION_PRECEDENCE]
        actionable.sort(key=lambda h: _ACTION_PRECEDENCE.get(h["composite_action"], 99))
        return actionable

    async def performance(self, portfolio_id: Optional[uuid.UUID] = None) -> dict[str, Any]:
        """Return portfolio performance totals using Decimal arithmetic."""
        stmt = select(AtlasPortfolioHolding).where(
            AtlasPortfolioHolding.is_deleted == False  # noqa: E712
        )
        if portfolio_id is not None:
            stmt = stmt.where(AtlasPortfolioHolding.portfolio_id == portfolio_id)

        query_out = await self._session.execute(stmt)
        rows = query_out.scalars().all()

        total_current = _D("0")
        total_cost = _D("0")
        for row in rows:
            if row.current_value is not None:
                total_current += Decimal(str(row.current_value))
            if row.cost_value is not None:
                total_cost += Decimal(str(row.cost_value))

        total_gain = total_current - total_cost
        gain_pct: Optional[Decimal] = None
        if total_cost > _D("0"):
            gain_pct = (total_gain / total_cost * _D("100")).quantize(_D("0.01"))

        return {
            "total_holdings": len(rows),
            "total_current_value": total_current,
            "total_cost_value": total_cost,
            "total_gain": total_gain,
            "gain_pct": gain_pct,
        }
