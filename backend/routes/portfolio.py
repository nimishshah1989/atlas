"""Portfolio routes — V4 endpoints.

POST /import-cams      — V4-2: CAMS PDF import (stub)
GET  /                 — V4-1: list portfolios
POST /create           — V4-1: create portfolio
GET  /{id}             — V4-1: get portfolio detail
PUT  /{id}             — V4-2: update portfolio (stub)
GET  /{id}/analysis    — V4-3: portfolio analysis (stub)
GET  /{id}/attribution — V4-4: attribution analysis (stub)
GET  /{id}/optimize    — V4-5: portfolio optimization (stub)

NOTE: static routes (/import-cams, /create) MUST be registered before /{id}
to prevent FastAPI treating the literal path segment as a UUID path parameter.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasPortfolio, AtlasPortfolioHolding
from backend.db.session import get_db
from backend.models.portfolio import (
    HoldingResponse,
    PortfolioCreateRequest,
    PortfolioListResponse,
    PortfolioResponse,
)
from backend.services.portfolio.repo import PortfolioRepo

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Static routes — MUST come before /{id} path param routes
# ---------------------------------------------------------------------------


@router.post("/import-cams", status_code=501)
async def import_cams(
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Import portfolio holdings from a CAMS PDF statement.

    Parses scheme names, folio numbers, and unit counts.
    Applies fuzzy matching to map schemes to mstar_id via JIP data.

    V4-2 implementation pending.
    """
    raise HTTPException(
        status_code=501,
        detail="CAMS import not yet implemented — coming in V4-2",
    )


@router.post("/create", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(
    request: PortfolioCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Create a new portfolio with optional initial holdings.

    Accepts a list of holdings; scheme-to-mstar_id mapping is performed
    asynchronously in V4-2. For now, holdings are stored with mapping_status='pending'.
    """
    repo = PortfolioRepo(session)

    portfolio = AtlasPortfolio(
        name=request.name,
        portfolio_type=request.portfolio_type.value,
        owner_type=request.owner_type.value,
        user_id=request.user_id,
    )

    holdings_orm: list[AtlasPortfolioHolding] = []
    for h in request.holdings:
        holding = AtlasPortfolioHolding(
            scheme_name=h.scheme_name,
            folio_number=h.folio_number,
            units=h.units,
            nav=h.nav,
            mstar_id=h.mstar_id,
            mapping_confidence=h.mapping_confidence,
            mapping_status=h.mapping_status.value,
        )
        holdings_orm.append(holding)

    async with session.begin():
        portfolio = await repo.create_portfolio(portfolio, holdings_orm)

    # Reload holdings after commit
    holdings_loaded = await repo.get_holdings(portfolio.id)

    return _build_portfolio_response(portfolio, holdings_loaded)


# ---------------------------------------------------------------------------
# Collection routes
# ---------------------------------------------------------------------------


@router.get("/", response_model=PortfolioListResponse)
async def list_portfolios(
    user_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    session: AsyncSession = Depends(get_db),
) -> PortfolioListResponse:
    """List all portfolios, newest first, excluding soft-deleted."""
    repo = PortfolioRepo(session)
    portfolios = await repo.list_portfolios(user_id=user_id, limit=limit)

    items = []
    for p in portfolios:
        holdings = await repo.get_holdings(p.id)
        items.append(_build_portfolio_response(p, holdings))

    return PortfolioListResponse(
        portfolios=items,
        count=len(items),
        data_as_of=datetime.datetime.now(tz=datetime.timezone.utc),
    )


# ---------------------------------------------------------------------------
# Item routes — MUST come after static routes
# ---------------------------------------------------------------------------


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Fetch full detail for a single portfolio by ID."""
    repo = PortfolioRepo(session)
    portfolio = await repo.get_portfolio(portfolio_id)

    if portfolio is None:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    holdings = await repo.get_holdings(portfolio_id)
    return _build_portfolio_response(portfolio, holdings)


@router.put("/{portfolio_id}", status_code=501)
async def update_portfolio(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update portfolio metadata.

    V4-2 implementation pending.
    """
    raise HTTPException(
        status_code=501,
        detail="Portfolio update not yet implemented — coming in V4-2",
    )


@router.get("/{portfolio_id}/analysis", status_code=501)
async def get_portfolio_analysis(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Return portfolio analysis snapshot (sector weights, quadrant distribution, RS).

    V4-3 implementation pending.
    """
    raise HTTPException(
        status_code=501,
        detail="Portfolio analysis not yet implemented — coming in V4-3",
    )


@router.get("/{portfolio_id}/attribution", status_code=501)
async def get_portfolio_attribution(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Return sector attribution for a portfolio.

    V4-4 implementation pending.
    """
    raise HTTPException(
        status_code=501,
        detail="Portfolio attribution not yet implemented — coming in V4-4",
    )


@router.get("/{portfolio_id}/optimize", status_code=501)
async def get_portfolio_optimize(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Return portfolio optimization suggestions.

    V4-5 implementation pending.
    """
    raise HTTPException(
        status_code=501,
        detail="Portfolio optimization not yet implemented — coming in V4-5",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_portfolio_response(
    portfolio: AtlasPortfolio,
    holdings: list[AtlasPortfolioHolding],
) -> PortfolioResponse:
    """Construct a PortfolioResponse from ORM objects."""
    from backend.models.portfolio import MappingStatus, OwnerType, PortfolioType

    holding_responses = [
        HoldingResponse(
            id=h.id,
            portfolio_id=h.portfolio_id,
            scheme_name=h.scheme_name,
            folio_number=h.folio_number,
            units=h.units,
            nav=h.nav,
            mstar_id=h.mstar_id,
            mapping_confidence=h.mapping_confidence,
            mapping_status=MappingStatus(h.mapping_status),
            current_value=h.current_value,
            cost_value=h.cost_value,
            created_at=h.created_at,
            updated_at=h.updated_at,
        )
        for h in holdings
    ]

    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        portfolio_type=PortfolioType(portfolio.portfolio_type),
        owner_type=OwnerType(portfolio.owner_type),
        user_id=portfolio.user_id,
        holdings=holding_responses,
        analysis_cache=portfolio.analysis_cache,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
    )
