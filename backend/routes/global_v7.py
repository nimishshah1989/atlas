"""V7-3 Global routes — /api/global prefix.

Routes:
    GET /api/global/ratios      — 9 macro series with 10-pt sparkline + MoM change
    GET /api/global/rs-heatmap  — 131 instruments grouped by instrument_type, total=131
    GET /api/global/indices     — global indices with four_bench_verdict + gold_rs_signal

All routes conform to spec §17 (UQL), §18 (include system), §20 (API principles).
Prefix is /api/global (not /api/v1/global — that prefix is owned by global_intel.py).
"""

from __future__ import annotations

import time
from collections import defaultdict
from decimal import Decimal
from typing import Optional

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_market_service import JIPMarketService
from backend.db.session import get_db
from backend.models.global_intel import MacroSparkItem
from backend.models.global_v7 import (
    FourBenchVerdict,
    GlobalIndexRow,
    GlobalIndicesResponse,
    GlobalInstrumentEntry,
    MacroRatioV7Item,
    MacroRatiosV7Response,
    RSHeatmapGroupedResponse,
)
from backend.models.schemas import ResponseMeta

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/global", tags=["global-v7"])


def _safe_decimal(v: object) -> Optional[Decimal]:
    """Convert DB value to Decimal. Returns None for None inputs."""
    if v is None:
        return None
    return Decimal(str(v))


def _compute_verdict(
    rs_composite: Optional[Decimal],
    rs_1m: Optional[Decimal],
    rs_3m: Optional[Decimal],
    gold_rs_signal: Optional[str],
) -> FourBenchVerdict:
    """Compute four-benchmark verdict.

    Each benchmark contributes 1 point if strictly positive (> 0).
    Nulls count as non-positive (0 points). Decimal("0") is not > 0.
    Score → verdict mapping:
        4 → STRONG_BUY
        3 → BUY
        2 → HOLD
        1 → CAUTION
        0 → AVOID
    """
    score = 0
    if rs_composite is not None and rs_composite > Decimal("0"):
        score += 1
    if rs_1m is not None and rs_1m > Decimal("0"):
        score += 1
    if rs_3m is not None and rs_3m > Decimal("0"):
        score += 1
    if gold_rs_signal == "AMPLIFIES_BULL":
        score += 1
    _verdict_map = {
        0: FourBenchVerdict.AVOID,
        1: FourBenchVerdict.CAUTION,
        2: FourBenchVerdict.HOLD,
        3: FourBenchVerdict.BUY,
        4: FourBenchVerdict.STRONG_BUY,
    }
    return _verdict_map[score]


@router.get(
    "/ratios",
    response_model=MacroRatiosV7Response,
    summary="Global Macro Ratios V7",
    description=(
        "Return 9 macro series (DGS10, VIXCLS, INDIAVIX, DXY, BRENT, GOLD, SP500, "
        "USDINR, FEDFUNDS) each with a 10-point sparkline and MoM change. "
        "MoM change = latest_value - value at ~30 trading days ago."
    ),
)
async def get_macro_ratios_v7(
    db: AsyncSession = Depends(get_db),
) -> MacroRatiosV7Response:
    """Return 9 macro series with sparkline + MoM change."""
    t0 = time.monotonic()
    svc = JIPMarketService(db)
    raw = await svc.get_macro_ratios_v7()
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    ratios: list[MacroRatioV7Item] = []
    for row in raw:
        spark_items: list[MacroSparkItem] = []
        for pt in row.get("sparkline") or []:
            spark_items.append(
                MacroSparkItem(
                    date=pt["date"],
                    value=_safe_decimal(pt.get("value")),
                )
            )
        ratios.append(
            MacroRatioV7Item(
                ticker=row["ticker"],
                name=row.get("name"),
                unit=row.get("unit"),
                latest_value=_safe_decimal(row.get("latest_value")),
                latest_date=row.get("latest_date"),
                mom_change=row.get("mom_change"),  # already Decimal from service
                sparkline=spark_items,
            )
        )

    meta = ResponseMeta(
        record_count=len(ratios),
        query_ms=elapsed_ms,
    )
    log.info("global_ratios_v7_served", count=len(ratios), elapsed_ms=elapsed_ms)
    return MacroRatiosV7Response(ratios=ratios, meta=meta)


@router.get(
    "/rs-heatmap",
    response_model=RSHeatmapGroupedResponse,
    summary="Global RS Heatmap (all 131 instruments, grouped by type)",
    description=(
        "Return all 131 global instruments from the master instrument table, "
        "grouped by instrument_type. Instruments without RS scores are still "
        "included (LEFT JOIN). total reflects all instrument rows."
    ),
)
async def get_global_rs_heatmap(
    db: AsyncSession = Depends(get_db),
) -> RSHeatmapGroupedResponse:
    """Return all 131 global instruments grouped by instrument_type."""
    t0 = time.monotonic()
    svc = JIPMarketService(db)
    rows = await svc.get_global_rs_heatmap_all()
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    by_type: dict[str, list[GlobalInstrumentEntry]] = defaultdict(list)
    for row in rows:
        itype = row.get("instrument_type") or "unknown"
        entry = GlobalInstrumentEntry(
            entity_id=row["entity_id"],
            name=row.get("name"),
            instrument_type=row.get("instrument_type"),
            country=row.get("country"),
            rs_composite=_safe_decimal(row.get("rs_composite")),
            rs_1m=_safe_decimal(row.get("rs_1m")),
            rs_3m=_safe_decimal(row.get("rs_3m")),
            rs_date=row.get("rs_date"),
            close=_safe_decimal(row.get("close")),
            price_date=row.get("price_date"),
        )
        by_type[itype].append(entry)

    total = len(rows)
    meta = ResponseMeta(
        record_count=total,
        query_ms=elapsed_ms,
    )
    log.info(
        "global_rs_heatmap_served",
        total=total,
        groups=len(by_type),
        elapsed_ms=elapsed_ms,
    )
    return RSHeatmapGroupedResponse(by_type=dict(by_type), total=total, meta=meta)


@router.get(
    "/indices",
    response_model=GlobalIndicesResponse,
    summary="Global Indices with Four-Benchmark Verdict",
    description=(
        "Return global indices (instrument_type='indices') with RS scores, "
        "gold_rs_signal from atlas_gold_rs_cache, and four_bench_verdict "
        "(STRONG_BUY|BUY|HOLD|CAUTION|AVOID). Nulls count as non-positive "
        "in verdict derivation."
    ),
)
async def get_global_indices(
    db: AsyncSession = Depends(get_db),
) -> GlobalIndicesResponse:
    """Return global indices with four_bench_verdict and gold_rs_signal."""
    t0 = time.monotonic()
    svc = JIPMarketService(db)
    rows = await svc.get_global_indices()
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    indices: list[GlobalIndexRow] = []
    for row in rows:
        rs_composite = _safe_decimal(row.get("rs_composite"))
        rs_1m = _safe_decimal(row.get("rs_1m"))
        rs_3m = _safe_decimal(row.get("rs_3m"))
        gold_rs_signal = row.get("gold_rs_signal")
        verdict = _compute_verdict(rs_composite, rs_1m, rs_3m, gold_rs_signal)
        indices.append(
            GlobalIndexRow(
                entity_id=row["entity_id"],
                name=row.get("name"),
                country=row.get("country"),
                rs_composite=rs_composite,
                rs_1m=rs_1m,
                rs_3m=rs_3m,
                rs_date=row.get("rs_date"),
                close=_safe_decimal(row.get("close")),
                price_date=row.get("price_date"),
                four_bench_verdict=verdict,
                gold_rs_signal=gold_rs_signal,
            )
        )

    meta = ResponseMeta(
        record_count=len(indices),
        query_ms=elapsed_ms,
    )
    log.info("global_indices_served", count=len(indices), elapsed_ms=elapsed_ms)
    return GlobalIndicesResponse(indices=indices, meta=meta)
