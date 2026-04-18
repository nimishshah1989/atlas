"""Analysis service — computes legacy and openbb signal sets from JIP data.

V11-9: OpenBB + FinanceToolkit pilot.

Legacy engine: minimal structured signal set from JIP stock_detail dict.
OpenBB engine: strict superset (all legacy keys + additional metrics).

No new external dependencies — pilot uses JIP data for both engines.
Real OpenBB/FinanceToolkit integration is a future upgrade path.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import structlog

from backend.core.computations import compute_quadrant
from backend.models.analysis import LegacySignals, OpenBBSignals
from backend.services.derived_signals import compute_piotroski

log = structlog.get_logger()


def _dec(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (ValueError, TypeError, ArithmeticError):
        return None


def build_legacy_signals(stock_detail: dict[str, Any]) -> LegacySignals:
    """Extract the minimum structured signal set from a JIP stock_detail row."""
    rs_c = _dec(stock_detail.get("rs_composite"))
    rs_m = _dec(stock_detail.get("rs_momentum"))
    macd_h = _dec(stock_detail.get("macd_histogram"))
    return LegacySignals(
        rs_composite=rs_c,
        rs_momentum=rs_m,
        rs_quadrant=compute_quadrant(rs_c, rs_m),
        rsi_14=_dec(stock_detail.get("rsi_14")),
        adx_14=_dec(stock_detail.get("adx_14")),
        macd_bullish=(macd_h > Decimal("0")) if macd_h is not None else None,
        above_200dma=stock_detail.get("above_200dma"),
        above_50dma=stock_detail.get("above_50dma"),
    )


async def build_openbb_signals(
    stock_detail: dict[str, Any],
    db: Any,
) -> OpenBBSignals:
    """Compute the OpenBB signal superset.

    All legacy signals plus additional metrics from JIP data.
    Piotroski score computed via existing derived_signals service.
    Falls back to None on any error (best-effort enrichment).
    """
    rs_c = _dec(stock_detail.get("rs_composite"))
    rs_m = _dec(stock_detail.get("rs_momentum"))
    macd_h = _dec(stock_detail.get("macd_histogram"))

    piotroski_score: Optional[int] = None
    try:
        pio = await compute_piotroski(stock_detail["id"], db)
        if pio is not None:
            piotroski_score = pio.score
    except Exception as exc:
        log.warning("piotroski_failed_in_openbb_engine", error=str(exc))

    return OpenBBSignals(
        # Legacy fields
        rs_composite=rs_c,
        rs_momentum=rs_m,
        rs_quadrant=compute_quadrant(rs_c, rs_m),
        rsi_14=_dec(stock_detail.get("rsi_14")),
        adx_14=_dec(stock_detail.get("adx_14")),
        macd_bullish=(macd_h > Decimal("0")) if macd_h is not None else None,
        above_200dma=stock_detail.get("above_200dma"),
        above_50dma=stock_detail.get("above_50dma"),
        # OpenBB-additional fields
        volatility_20d=_dec(stock_detail.get("volatility_20d")),
        beta_nifty=_dec(stock_detail.get("beta_nifty")),
        sharpe_1y=_dec(stock_detail.get("sharpe_1y")),
        sortino_1y=_dec(stock_detail.get("sortino_1y")),
        max_drawdown_1y=_dec(stock_detail.get("max_drawdown_1y")),
        piotroski_score=piotroski_score,
        macd_line=_dec(stock_detail.get("macd_line")),
        macd_signal_line=_dec(stock_detail.get("macd_signal")),
        bollinger_upper=_dec(stock_detail.get("bollinger_upper")),
        bollinger_lower=_dec(stock_detail.get("bollinger_lower")),
        stochastic_k=_dec(stock_detail.get("stochastic_k")),
        stochastic_d=_dec(stock_detail.get("stochastic_d")),
        disparity_20=_dec(stock_detail.get("disparity_20")),
    )
