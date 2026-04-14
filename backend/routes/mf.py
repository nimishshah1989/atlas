"""ATLAS V2 MF (mutual fund) API — router skeleton.

This chunk (V2-1) defines the contract surface only. Every endpoint is
mounted with its Pydantic `response_model`, but data wiring lands in
later V2 chunks (V2-2 JIP client extension, V2-3 computations, V2-4+
service layer). Until then, calls return `501 Not Implemented` so we
never serve synthetic data — see CLAUDE.md, Four Laws #2.
"""

from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query

from backend.services.uql import engine as uql_engine
from backend.models.mf import (
    CategoriesResponse,
    FlowsResponse,
    FundDeepDiveResponse,
    FundRSHistoryResponse,
    FundSectorsResponse,
    HoldingsResponse,
    HoldingStockResponse,
    NAVHistoryResponse,
    OverlapResponse,
    UniverseResponse,
    WeightedTechnicalsResponse,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/mf", tags=["mf"])


_NOT_IMPL = "MF endpoint not yet wired (V2-1 contract skeleton)"

LEGACY_ENDPOINT_IDS: tuple[str, ...] = (
    "mf.universe",
    "mf.categories",
    "mf.flows",
    "mf.overlap",
    "mf.holding_stock",
    "mf.deep_dive",
    "mf.holdings",
    "mf.sectors",
    "mf.rs_history",
    "mf.weighted_technicals",
    "mf.nav_history",
)


def build_uql_request(endpoint_id: str, params: dict[str, Any]) -> Any:
    """Translate a legacy mf endpoint call into a UQLRequest.

    Thin shim onto :func:`uql_engine.build_from_legacy`. Per spec §17/§20
    every fixed endpoint must be expressible as a UQL request; the engine
    grows one branch per id. Currently delegates straight through — when a
    later V2 chunk wires real data, route handlers swap their JIPDataService
    calls for ``await uql_engine.execute(build_uql_request(...))`` without
    changing this seam.
    """
    return uql_engine.build_from_legacy(endpoint_id, params)


def _not_implemented() -> HTTPException:
    return HTTPException(status_code=501, detail=_NOT_IMPL)


@router.get("/universe", response_model=UniverseResponse)
async def get_universe(
    benchmark: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    broad_category: Optional[str] = Query(None),
    active_only: Optional[bool] = Query(True),
) -> UniverseResponse:
    raise _not_implemented()


@router.get("/categories", response_model=CategoriesResponse)
async def get_categories() -> CategoriesResponse:
    raise _not_implemented()


@router.get("/flows", response_model=FlowsResponse)
async def get_flows(months: Optional[int] = Query(12, ge=1, le=120)) -> FlowsResponse:
    raise _not_implemented()


@router.get("/overlap", response_model=OverlapResponse)
async def get_overlap(
    funds: str = Query(..., description="Comma-separated mstar_ids: A,B"),
) -> OverlapResponse:
    raise _not_implemented()


@router.get("/holding-stock/{symbol}", response_model=HoldingStockResponse)
async def get_holding_stock(symbol: str) -> HoldingStockResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/holdings", response_model=HoldingsResponse)
async def get_fund_holdings(mstar_id: str) -> HoldingsResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/sectors", response_model=FundSectorsResponse)
async def get_fund_sectors(mstar_id: str) -> FundSectorsResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/rs-history", response_model=FundRSHistoryResponse)
async def get_fund_rs_history(
    mstar_id: str,
    months: Optional[int] = Query(12, ge=1, le=120),
) -> FundRSHistoryResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/weighted-technicals", response_model=WeightedTechnicalsResponse)
async def get_fund_weighted_technicals(mstar_id: str) -> WeightedTechnicalsResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/nav-history", response_model=NAVHistoryResponse)
async def get_fund_nav_history(
    mstar_id: str,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
) -> NAVHistoryResponse:
    raise _not_implemented()


@router.get("/{mstar_id}", response_model=FundDeepDiveResponse)
async def get_fund_deep_dive(mstar_id: str) -> FundDeepDiveResponse:
    raise _not_implemented()
