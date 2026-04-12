"""ATLAS core computations — pure domain logic, no HTTP, no DB imports.

RS momentum, quadrant classification, conviction assessment.
All financial values use Decimal.
"""

from decimal import Decimal
from typing import Any, Optional

from backend.models.schemas import (
    ConvictionPillars,
    PillarInstitutional,
    PillarRS,
    PillarTechnical,
    Quadrant,
    TechnicalCheck,
)


def _dec(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    return Decimal(str(val))


def compute_quadrant(
    rs_composite: Optional[Decimal], rs_momentum: Optional[Decimal]
) -> Optional[Quadrant]:
    """Classify into RRG quadrant based on RS composite and momentum."""
    if rs_composite is None or rs_momentum is None:
        return None
    if rs_composite > 0 and rs_momentum > 0:
        return Quadrant.LEADING
    elif rs_composite < 0 and rs_momentum > 0:
        return Quadrant.IMPROVING
    elif rs_composite > 0 and rs_momentum < 0:
        return Quadrant.WEAKENING
    else:
        return Quadrant.LAGGING


def build_conviction_pillars(stock_data: dict[str, Any]) -> ConvictionPillars:
    """Build 4 conviction pillars from stock data. Each pillar is EXPLAINED, not scored."""

    rs_composite = _dec(stock_data.get("rs_composite"))
    rs_momentum = _dec(stock_data.get("rs_momentum"))
    quadrant = compute_quadrant(rs_composite, rs_momentum)

    # --- Pillar 1: Relative Strength ---
    rs_parts = []
    if rs_composite is not None:
        sign = "+" if rs_composite > 0 else ""
        rs_parts.append(f"RS is {sign}{rs_composite} vs NIFTY 500")
    if rs_momentum is not None:
        direction = "improving" if rs_momentum > 0 else "deteriorating"
        rs_parts.append(f"momentum {direction} ({rs_momentum:+})")
    if quadrant:
        rs_parts.append(f"quadrant: {quadrant.value}")

    pillar_rs = PillarRS(
        rs_composite=rs_composite,
        rs_momentum=rs_momentum,
        rs_1w=_dec(stock_data.get("rs_1w")),
        rs_1m=_dec(stock_data.get("rs_1m")),
        rs_3m=_dec(stock_data.get("rs_3m")),
        rs_6m=_dec(stock_data.get("rs_6m")),
        rs_12m=_dec(stock_data.get("rs_12m")),
        quadrant=quadrant,
        benchmark="NIFTY 500",
        explanation=". ".join(rs_parts) if rs_parts else "No RS data available",
    )

    # --- Pillar 2: Technical Health (10 checks) ---
    checks = _build_technical_checks(stock_data)
    passing = sum(1 for c in checks if c.passing)

    check_details = []
    for c in checks:
        status = "passing" if c.passing else "failing"
        check_details.append(f"{c.name}: {c.detail} ({status})")

    pillar_tech = PillarTechnical(
        checks_passing=passing,
        checks_total=len(checks),
        checks=checks,
        explanation=f"{passing}/{len(checks)} checks passing. "
        + "; ".join(check_details[:5]),
    )

    # --- Pillar 3: Institutional ---
    mf_count = stock_data.get("mf_holder_count")
    delivery = _dec(stock_data.get("delivery_vs_avg"))

    inst_parts = []
    if mf_count is not None:
        inst_parts.append(f"{mf_count} MFs hold this stock")
    if delivery is not None:
        level = "above" if delivery > Decimal("1") else "below"
        inst_parts.append(f"delivery {level} average ({delivery}x)")

    pillar_inst = PillarInstitutional(
        mf_holder_count=mf_count,
        delivery_vs_avg=delivery,
        explanation=". ".join(inst_parts)
        if inst_parts
        else "No institutional data available",
    )

    return ConvictionPillars(
        rs=pillar_rs,
        technical=pillar_tech,
        institutional=pillar_inst,
    )


_TECHNICAL_CHECK_DEFS: list[tuple[str, str, Any, Any]] = [
    (
        "Above 200 DMA",
        "above_200dma",
        lambda v: v is True,
        lambda v, p: "Price above 200-day MA" if p else "Price below 200-day MA",
    ),
    (
        "Above 50 DMA",
        "above_50dma",
        lambda v: v is True,
        lambda v, p: "Price above 50-day MA" if p else "Price below 50-day MA",
    ),
    (
        "RSI Healthy",
        "rsi_14",
        lambda v: Decimal("30") <= v <= Decimal("70"),
        lambda v, p: f"RSI {v} ({'healthy' if p else 'extreme'})",
    ),
    (
        "ADX Trending",
        "adx_14",
        lambda v: v > Decimal("25"),
        lambda v, p: f"ADX {v} ({'trending' if p else 'weak trend'})",
    ),
    (
        "MACD Bullish",
        "macd_histogram",
        lambda v: v > 0,
        lambda v, p: f"MACD histogram {'positive' if p else 'negative'}",
    ),
    ("MFI Healthy", "mfi_14", lambda v: v > Decimal("40"), lambda v, p: f"MFI {v}"),
    ("Positive Sharpe", "sharpe_1y", lambda v: v > 0, lambda v, p: f"Sharpe 1Y: {v}"),
    (
        "Adequate Volume",
        "relative_volume",
        lambda v: v > Decimal("0.8"),
        lambda v, p: f"Relative volume {v}x",
    ),
    (
        "Manageable Volatility",
        "volatility_20d",
        lambda v: v < Decimal("40"),
        lambda v, p: f"20d volatility {v}%",
    ),
    (
        "Acceptable Drawdown",
        "max_drawdown_1y",
        lambda v: v > Decimal("-30"),
        lambda v, p: f"Max drawdown 1Y: {v}%",
    ),
]


def _evaluate_check(
    name: str, raw_value: Any, test_fn: Any, detail_fn: Any
) -> TechnicalCheck:
    """Evaluate a single technical check against a raw data value."""
    converted = _dec(raw_value) if not isinstance(raw_value, bool) else raw_value
    if converted is None and not isinstance(raw_value, bool):
        return TechnicalCheck(
            name=name, passing=False, value="N/A", detail=f"{name}: no data"
        )
    passing = test_fn(converted)
    return TechnicalCheck(
        name=name,
        passing=passing,
        value=str(converted),
        detail=detail_fn(converted, passing),
    )


def _build_technical_checks(stock_data: dict[str, Any]) -> list[TechnicalCheck]:
    """Build 10 technical health checks from stock data."""
    return [
        _evaluate_check(name, stock_data.get(field_key), test_fn, detail_fn)
        for name, field_key, test_fn, detail_fn in _TECHNICAL_CHECK_DEFS
    ]
