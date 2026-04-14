"""Portfolio routes — V4 endpoints.

POST /import-cams      — V4-2: CAMS PDF import
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
from datetime import date
from decimal import Decimal
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_mf_service import JIPMFService
from backend.db.models import AtlasPortfolio, AtlasPortfolioHolding
from backend.db.session import get_db
from backend.models.portfolio import (
    HoldingResponse,
    MappingStatus,
    PortfolioAttributionResponse,
    PortfolioCreateRequest,
    PortfolioFullAnalysisResponse,
    PortfolioImportResult,
    PortfolioListResponse,
    PortfolioResponse,
)
from backend.services.portfolio.analysis import PortfolioAnalysisService
from backend.services.portfolio.attribution import BrinsonAttributionService
from backend.services.portfolio.cams_import import CamsImportError, CamsParseResult, parse_cas_pdf
from backend.services.portfolio.repo import PortfolioRepo
from backend.services.portfolio.scheme_mapper import MappedHolding, SchemeMapper

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Static routes — MUST come before /{id} path param routes
# ---------------------------------------------------------------------------


@router.post("/import-cams", response_model=PortfolioImportResult, status_code=201)
async def import_cams(
    file: UploadFile,
    password: Optional[str] = Form(default=None),
    portfolio_name: Optional[str] = Form(default=None),
    user_id: Optional[str] = Form(default=None),
    session: AsyncSession = Depends(get_db),
) -> PortfolioImportResult:
    """Import portfolio holdings from a CAMS/KFintech CAS PDF statement.

    Parses scheme names, folio numbers, and unit counts via casparser.
    Applies fuzzy matching to map schemes to mstar_id via the JIP MF master table.
    Manual overrides in atlas_scheme_mapping_overrides short-circuit fuzzy match.

    Raw PDF bytes are processed in-memory and never stored permanently.
    """
    # Read and parse file — never store raw PDF
    try:
        file_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to read uploaded file: {exc}") from exc

    if not file_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    try:
        parse_result = parse_cas_pdf(file_bytes, password=password)
    except CamsImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    log.info("cams_import_parsed", holdings=len(parse_result.holdings))

    name = _resolve_portfolio_name(portfolio_name, parse_result.investor_name)
    scheme_names = [h.scheme_name for h in parse_result.holdings]
    mapped = await SchemeMapper(session).map_holdings(scheme_names)

    portfolio_orm, holdings_orm = _build_cams_orm(name, user_id, parse_result, mapped)
    repo = PortfolioRepo(session)
    async with session.begin():
        portfolio_orm = await repo.create_portfolio(portfolio_orm, holdings_orm)

    holdings_loaded = await repo.get_holdings(portfolio_orm.id)
    return _build_import_result(portfolio_orm, holdings_loaded)


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


@router.get("/{portfolio_id}/analysis", response_model=PortfolioFullAnalysisResponse)
async def get_portfolio_analysis(
    portfolio_id: uuid.UUID,
    data_as_of: Optional[date] = Query(
        default=None,
        description="Date for analysis (ISO 8601). Defaults to today.",
    ),
    session: AsyncSession = Depends(get_db),
) -> PortfolioFullAnalysisResponse:
    """Return full portfolio analysis: per-holding JIP enrichment + portfolio-level aggregates.

    Per-holding metrics (from JIP): NAV + returns, RS composite + momentum + quadrant,
    derived metrics (Sharpe, Sortino, Alpha, Beta), weighted technicals (RSI, breadth, MACD),
    sector exposure.

    Portfolio-level aggregates: weighted RS (value-weighted), sector concentration,
    quadrant distribution, weighted average Sharpe/Sortino/Beta, pairwise fund overlap.

    Graceful degradation: if JIP data is unavailable for a holding, it appears
    in the `unavailable` list and the analysis continues with remaining holdings.
    """
    repo = PortfolioRepo(session)
    jip = JIPMFService(session)
    service = PortfolioAnalysisService(repo=repo, jip=jip)

    try:
        analysis = await service.analyze_portfolio(
            portfolio_id=portfolio_id,
            data_as_of=data_as_of,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return analysis


@router.get("/{portfolio_id}/attribution", response_model=PortfolioAttributionResponse)
async def get_portfolio_attribution(
    portfolio_id: uuid.UUID,
    data_as_of: Optional[date] = Query(
        default=None,
        description="Date for attribution (ISO 8601). Defaults to today.",
    ),
    session: AsyncSession = Depends(get_db),
) -> PortfolioAttributionResponse:
    """Return Brinson-Fachler attribution analysis for a portfolio.

    Computes allocation, selection, and interaction effects per MF category.

    Brinson-Fachler model:
      allocation_effect   = (w_p - w_b) * (R_b_sector - R_b_total)
      selection_effect    = w_b * (R_p_sector - R_b_sector)
      interaction_effect  = (w_p - w_b) * (R_p_sector - R_b_sector)

    Where:
      w_p = portfolio weight in category (value / total_value)
      w_b = benchmark weight (active_fund_count / total_active_funds, equal-weight)
      R_b_sector = category avg 1Y return from NAV history (via JIP MF service)
      R_p_sector = value-weighted avg manager_alpha for portfolio holdings in category

    Returns returns_available=False when NAV history is insufficient for benchmark
    returns. Category weights are always computed.

    Response includes formula, tolerance, and data_as_of for full traceability.
    """
    repo = PortfolioRepo(session)
    jip = JIPMFService(session)
    service = BrinsonAttributionService(repo=repo, jip=jip)

    try:
        attribution = await service.compute_attribution(
            portfolio_id=portfolio_id,
            data_as_of=data_as_of,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return attribution


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


def _resolve_portfolio_name(
    requested: Optional[str],
    investor_name: Optional[str],
) -> str:
    """Determine the portfolio name from form input or CAS investor info."""
    if requested:
        return requested
    if investor_name:
        return f"{investor_name} — CAMS Import"
    return f"CAMS Import {datetime.datetime.now(tz=datetime.timezone.utc).strftime('%Y-%m-%d')}"


def _build_cams_orm(
    name: str,
    user_id: Optional[str],
    parse_result: CamsParseResult,
    mapped: list[MappedHolding],
) -> tuple[AtlasPortfolio, list[AtlasPortfolioHolding]]:
    """Build portfolio + holdings ORM objects from parsed + mapped data."""
    portfolio = AtlasPortfolio(
        name=name,
        portfolio_type="cams_import",
        owner_type="retail",
        user_id=user_id,
    )
    holdings_orm: list[AtlasPortfolioHolding] = []
    for parsed, mapping in zip(parse_result.holdings, mapped):
        current_value: Optional[Decimal] = None
        if parsed.units and parsed.nav is not None:
            current_value = parsed.units * parsed.nav
        holdings_orm.append(
            AtlasPortfolioHolding(
                scheme_name=parsed.scheme_name,
                folio_number=parsed.folio_number,
                units=parsed.units,
                nav=parsed.nav,
                current_value=current_value,
                mstar_id=mapping.mstar_id,
                mapping_confidence=mapping.confidence,
                mapping_status=mapping.mapping_status.value,
            )
        )
    return portfolio, holdings_orm


def _build_import_result(
    portfolio: AtlasPortfolio,
    holdings_loaded: list[AtlasPortfolioHolding],
) -> PortfolioImportResult:
    """Assemble PortfolioImportResult from persisted ORM objects."""
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
        for h in holdings_loaded
    ]
    needs_review = [hr for hr in holding_responses if hr.mapping_status == MappingStatus.pending]
    mapped_count = sum(1 for hr in holding_responses if hr.mapping_status == MappingStatus.mapped)
    override_count = sum(
        1 for hr in holding_responses if hr.mapping_status == MappingStatus.manual_override
    )
    log.info(
        "cams_import_complete",
        portfolio_id=str(portfolio.id),
        total=len(holding_responses),
        mapped=mapped_count + override_count,
        pending=len(needs_review),
    )
    return PortfolioImportResult(
        portfolio_id=portfolio.id,
        portfolio_name=portfolio.name,
        holdings=holding_responses,
        needs_review=needs_review,
        mapped_count=mapped_count + override_count,
        pending_count=len(needs_review),
        total_count=len(holding_responses),
        data_as_of=datetime.datetime.now(tz=datetime.timezone.utc),
    )


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
