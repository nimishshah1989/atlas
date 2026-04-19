"""MF Top-RS and 4-Factor Rank endpoints — extracted from mf.py for modularity."""

from collections import defaultdict
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.clients.sql_fragments import safe_decimal
from backend.db.session import get_db
from backend.services.mf_compute import classify_fund_quadrant

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/mf", tags=["mf"])


# ── Top-RS response models ────────────────────────────────────────────────────


class TopRSFund(BaseModel):
    mstar_id: str
    fund_name: str
    rs_composite: Optional[Decimal]
    category_name: Optional[str]
    quadrant: Optional[str]


class TopRSMeta(BaseModel):
    data_as_of: Optional[str]
    staleness_seconds: int = 0
    source: str = "jip/mf_derived"


class TopRSResponse(BaseModel):
    model_config = {"populate_by_name": True}

    funds: list[TopRSFund]
    _meta: TopRSMeta


@router.get("/top-rs", response_model=None)
async def get_top_rs_funds(
    limit: Optional[int] = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Top N mutual funds by RS composite — lightweight alternative to /universe.

    Returns `{ data: [...], _meta: {...} }` format (spec §18).
    """
    svc = JIPDataService(db)
    try:
        rows = await svc.get_top_rs_funds()
    except (OSError, RuntimeError, ValueError) as _err:
        log.warning("top_rs_fetch_failed", error=str(_err))
        rows = []

    all_funds: list[dict[str, Any]] = list(rows)
    all_funds.sort(
        key=lambda r: safe_decimal(r.get("rs_composite")) or Decimal("0"),
        reverse=True,
    )
    top_n = all_funds[:limit] if limit else all_funds[:5]

    nav_date_val = top_n[0].get("nav_date") if top_n else None
    data_as_of_val: Optional[str] = str(nav_date_val) if nav_date_val else None

    funds_out = []
    for r in top_n:
        rs = safe_decimal(r.get("rs_composite"))
        quadrant = classify_fund_quadrant(rs, None)
        funds_out.append(
            {
                "mstar_id": str(r["mstar_id"]),
                "fund_name": str(r["fund_name"]),
                "rs_composite": rs,
                "category_name": r.get("category_name"),
                "quadrant": quadrant,
            }
        )

    return {
        "data": funds_out,
        "_meta": {
            "data_as_of": data_as_of_val,
            "staleness_seconds": 0,
            "source": "jip/mf_derived",
        },
    }


# ── 4-Factor MF Rank helpers ─────────────────────────────────────────────────

_NEG_INF = Decimal("-Infinity")


def _percent_rank_asc(values: list[Any]) -> list[Decimal]:
    """Assign 0-100 percentile scores; highest raw value → 100."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [Decimal("50")]
    decimals: list[Decimal] = [(Decimal(str(v)) if v is not None else _NEG_INF) for v in values]
    order = sorted(range(n), key=lambda i: decimals[i])
    ranks: list[Decimal] = [Decimal("0")] * n
    denom = Decimal(str(n - 1))
    for pos, orig in enumerate(order):
        ranks[orig] = Decimal(str(pos)) / denom * Decimal("100")
    return ranks


def _percent_rank_desc(values: list[Any]) -> list[Decimal]:
    """Assign 0-100 percentile scores; lowest raw value → 100 (inverted)."""
    negated: list[Any] = [(-Decimal(str(v)) if v is not None else None) for v in values]
    return _percent_rank_asc(negated)


def _compute_rank_scores(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Score all funds on 4 factors within category, then rank globally."""
    by_cat: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        by_cat[row["category_name"]].append(i)

    ret_s: list[Optional[Decimal]] = [None] * len(rows)
    rsk_s: list[Optional[Decimal]] = [None] * len(rows)
    res_s: list[Optional[Decimal]] = [None] * len(rows)
    con_s: list[Optional[Decimal]] = [None] * len(rows)

    for idxs in by_cat.values():
        sharpes = [rows[i]["sharpe_1y"] for i in idxs]
        vols = [rows[i]["volatility_1y"] for i in idxs]
        dds = [rows[i]["max_drawdown_1y"] for i in idxs]
        irs = [rows[i]["information_ratio"] for i in idxs]

        sr = _percent_rank_asc(sharpes)  # higher sharpe = better
        vr = _percent_rank_desc(vols)  # lower vol = better
        dr = _percent_rank_asc(dds)  # less-negative drawdown = better
        ir = _percent_rank_asc(irs)  # higher IR = better

        for j, orig in enumerate(idxs):
            ret_s[orig] = sr[j]
            rsk_s[orig] = vr[j]
            res_s[orig] = dr[j]
            con_s[orig] = ir[j]

    enriched: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        rs, rk, rl, cs_ = ret_s[i], rsk_s[i], res_s[i], con_s[i]
        scores: list[Decimal] = [s for s in [rs, rk, rl, cs_] if s is not None]
        composite: Optional[Decimal] = sum(scores, Decimal("0")) / len(scores) if scores else None
        nav_date = row.get("nav_date")
        enriched.append(
            {
                "mstar_id": row["mstar_id"],
                "fund_name": row["fund_name"],
                "category": row["category_name"],
                "aum_cr": None,
                "sparkline": None,
                "ret_1y": None,
                "ret_3y": None,
                "ret_5y": None,
                "returns_score": round(rs, 1) if rs is not None else None,
                "risk_score": round(rk, 1) if rk is not None else None,
                "resilience_score": round(rl, 1) if rl is not None else None,
                "consistency_score": round(cs_, 1) if cs_ is not None else None,
                "composite_score": round(composite, 2) if composite is not None else None,
                "_nav_date": str(nav_date) if nav_date else None,
            }
        )

    enriched.sort(
        key=lambda r: (
            -(r["composite_score"] or 0),
            -(r["consistency_score"] or 0),
            -(r["risk_score"] or 0),
            -(r["returns_score"] or 0),
            -(r["resilience_score"] or 0),
        )
    )
    for rank_idx, r in enumerate(enriched):
        r["rank"] = rank_idx + 1

    return enriched


@router.get("/rank", response_model=None)
async def get_mf_rank(
    category: Optional[str] = Query(None, description="Filter by category_name"),
    aum_range: Optional[str] = Query(None, description="large|mid|small — reserved"),
    limit: Optional[int] = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """4-factor composite ranking of active mutual funds.

    Factors (25% weight each):
    - Returns: Sharpe 1Y percentile within category (higher = better)
    - Risk: Volatility 1Y inverted percentile (lower vol = better)
    - Resilience: Max drawdown 1Y percentile (less-negative = better)
    - Consistency: Information ratio percentile (higher = better)

    Scores are percentile-ranked within category (0–100).
    Composite is the simple average; tie-break: Consistency → Risk → Returns → Resilience.
    """
    svc = JIPDataService(db)
    try:
        raw_rows = await svc.get_mf_rank_data()
    except (OSError, RuntimeError, ValueError, LookupError) as exc:
        log.error("mf_rank_fetch_failed", error=str(exc))
        raw_rows = []

    if not raw_rows:
        return {
            "records": [],
            "_meta": {
                "data_as_of": None,
                "staleness_seconds": 0,
                "source": "jip/mf_derived",
                "total": 0,
            },
        }

    scored = _compute_rank_scores(raw_rows)

    if category:
        scored = [r for r in scored if r["category"] == category]
        for rank_idx, r in enumerate(scored):
            r["rank"] = rank_idx + 1

    effective_limit = limit if limit is not None else 100
    page = scored[:effective_limit]

    nav_dates = [r["_nav_date"] for r in page if r.get("_nav_date")]
    data_as_of_val = max(nav_dates) if nav_dates else None

    for r in page:
        r.pop("_nav_date", None)

    log.info(
        "mf_rank_route_complete",
        total_scored=len(scored),
        returned=len(page),
        category_filter=category,
        data_as_of=data_as_of_val,
    )

    return {
        "records": page,
        "_meta": {
            "data_as_of": data_as_of_val,
            "staleness_seconds": 0,
            "source": "jip/mf_derived",
            "total": len(scored),
        },
    }
