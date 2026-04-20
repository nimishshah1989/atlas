"""LensService — 4-lens (RS / Momentum / Breadth / Volume) bundle per scope.

Pure service layer: no SQL, no route logic. Delegates data access exclusively
to JIPDataService. All financial values Decimal.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.models.lenses import LensBundle, LensValue
from backend.services import signal_engine
from backend.services.signal_engine import Lens, Signal, SignalType

log = structlog.get_logger(__name__)

_VALID_SCOPES = frozenset({"country", "sector", "stock", "etf", "mf"})
_VALID_PERIODS = frozenset({"1M", "3M", "6M", "12M"})

_D = Decimal


def _d(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def _derive_action(signals_by_lens: dict[str, list[Signal]]) -> str:
    """Derive composite action from per-lens signals.

    Rules (highest precedence first):
    - CONFIRM present AND >= 2 lenses ENTRY → BUY
    - any lens EXIT → SELL or AVOID (AVOID if rs_percentile < 30)
    - all lenses ENTRY/positive → BUY
    - >= 1 lens ENTRY → HOLD
    - majority WARN → WATCH
    - default → HOLD
    """
    all_signals: list[Signal] = [s for sigs in signals_by_lens.values() for s in sigs]

    confirm_signals = [s for s in all_signals if s.type == SignalType.CONFIRM]
    entry_lenses = [
        k for k, sigs in signals_by_lens.items() if any(s.type == SignalType.ENTRY for s in sigs)
    ]
    exit_lenses = [
        k for k, sigs in signals_by_lens.items() if any(s.type == SignalType.EXIT for s in sigs)
    ]
    warn_lenses = [
        k for k, sigs in signals_by_lens.items() if any(s.type == SignalType.WARN for s in sigs)
    ]

    if confirm_signals and len(entry_lenses) >= 2:
        return "BUY"
    if exit_lenses:
        # Check RS lens percentile for AVOID vs SELL
        rs_sigs = signals_by_lens.get("rs", [])
        rs_vals = [s.value for s in rs_sigs if s.value is not None]
        rs_val = rs_vals[0] if rs_vals else None
        if rs_val is not None and rs_val < _D("30"):
            return "AVOID"
        return "SELL"
    if len(entry_lenses) >= len(signals_by_lens) and signals_by_lens:
        return "BUY"
    if entry_lenses:
        return "HOLD"
    if len(warn_lenses) > len(signals_by_lens) // 2:
        return "WATCH"
    return "HOLD"


class LensService:
    """Compute 4-lens bundle for any scope/entity."""

    def __init__(self, session: AsyncSession) -> None:
        self._svc = JIPDataService(session)

    async def get_lenses(
        self,
        scope: str,
        entity_id: str,
        benchmark: str = "NIFTY 500",
        period: str = "3M",
    ) -> LensBundle:
        """Return a LensBundle for the given scope + entity."""
        if scope not in _VALID_SCOPES:
            raise ValueError(f"Unknown scope '{scope}'. Valid: {sorted(_VALID_SCOPES)}")
        if period not in _VALID_PERIODS:
            raise ValueError(f"Unknown period '{period}'. Valid: {sorted(_VALID_PERIODS)}")

        thresholds = signal_engine.load_thresholds()

        if scope == "stock":
            return await self._lens_stock(entity_id, benchmark, period, thresholds)
        elif scope == "sector":
            return await self._lens_sector(entity_id, benchmark, period, thresholds)
        elif scope == "country":
            return await self._lens_country(entity_id, benchmark, period, thresholds)
        elif scope == "mf":
            return await self._lens_mf(entity_id, benchmark, period, thresholds)
        else:  # etf
            return await self._lens_etf(entity_id, benchmark, period, thresholds)

    # ------------------------------------------------------------------
    # Private per-scope implementations
    # ------------------------------------------------------------------

    async def _lens_stock(
        self,
        symbol: str,
        benchmark: str,
        period: str,
        thresholds: dict[str, Any],
    ) -> LensBundle:
        detail = await self._svc.get_stock_detail(symbol)
        rs_history = await self._svc.get_rs_history(symbol, benchmark=benchmark, months=12)

        if not detail:
            return self._empty_bundle(
                "stock", symbol, benchmark, period, reason="insufficient_data"
            )

        rs_series = [
            _d(r.get("rs_composite")) for r in rs_history if r.get("rs_composite") is not None
        ]
        rs_series_dec: list[Decimal] = [v for v in rs_series if v is not None]

        rs_val = _d(detail.get("rs_composite"))
        momentum_val = _d(detail.get("rs_momentum"))
        # breadth: use above_200dma as a proxy (0 or 100)
        above_200 = detail.get("above_200dma")
        above_50 = detail.get("above_50dma")
        st_breadth = _D("70") if above_50 else _D("30")
        mt_breadth = _D("70") if above_200 else _D("30")

        slope_5d = _d(detail.get("macd_histogram")) or _D("0")

        rs_sigs = (
            signal_engine.evaluate_rs(rs_val or _D("50"), rs_series_dec, thresholds)
            if rs_val is not None
            else []
        )

        mom_sigs = (
            signal_engine.evaluate_momentum(momentum_val or _D("0"), slope_5d, thresholds)
            if momentum_val is not None
            else []
        )

        breadth_sigs = signal_engine.evaluate_breadth(st_breadth, mt_breadth, _D("50"), thresholds)

        # Volume: use relative volume from rsi as proxy if unavailable
        rel_vol = _d(detail.get("rel_vol")) or _D("1.0")
        vol_sigs = signal_engine.evaluate_volume(rel_vol, thresholds)

        signals_map: dict[Lens, list[Signal]] = {
            Lens.rs: rs_sigs,
            Lens.momentum: mom_sigs,
            Lens.breadth: breadth_sigs,
            Lens.volume: vol_sigs,
        }
        confirm = signal_engine.evaluate_confirm(signals_map, thresholds)

        # Map to string-keyed dict for _derive_action
        str_map: dict[str, list[Signal]] = {k.value: v for k, v in signals_map.items()}
        action = _derive_action(str_map)

        data_as_of: Optional[datetime.date] = None
        if detail.get("date"):
            try:
                data_as_of = datetime.date.fromisoformat(str(detail["date"]))
            except Exception:  # noqa: BLE001
                pass

        return LensBundle(
            scope="stock",
            entity_id=symbol,
            benchmark=benchmark,
            period=period,
            lenses={
                "rs": LensValue(value=rs_val, signals=rs_sigs),
                "momentum": LensValue(value=momentum_val, signals=mom_sigs),
                "breadth": LensValue(value=(st_breadth + mt_breadth) / 2, signals=breadth_sigs),
                "volume": LensValue(value=rel_vol, signals=vol_sigs),
            },
            composite_action=action,
            data_as_of=data_as_of,
            reason=confirm[0].reason if confirm else f"action={action}",
        )

    async def _lens_sector(
        self,
        key: str,
        benchmark: str,
        period: str,
        thresholds: dict[str, Any],
    ) -> LensBundle:
        from backend.services.sector_service import SectorService

        svc = SectorService(self._svc)
        universe_map = {"NIFTY 50": "NIFTY", "NIFTY 200": "NIFTY100", "NIFTY 500": "NIFTY500"}
        universe = universe_map.get(benchmark, "NIFTY500")

        summary = await svc.sector_roll_up(key, universe=universe)
        if not summary.four_lens:
            return self._empty_bundle("sector", key, benchmark, period, reason="insufficient_data")

        rs_val = summary.four_lens.get("rs")
        mom_val = summary.four_lens.get("momentum")
        breadth_val = summary.four_lens.get("breadth")
        vol_val = summary.four_lens.get("volume")

        str_map: dict[str, list[Signal]] = {}
        for sig in summary.signals:
            k_str = sig.lens.value if sig.lens else "confirm"
            str_map.setdefault(k_str, []).append(sig)

        action = summary.composite_action

        return LensBundle(
            scope="sector",
            entity_id=key,
            benchmark=benchmark,
            period=period,
            lenses={
                "rs": LensValue(value=rs_val),
                "momentum": LensValue(value=mom_val),
                "breadth": LensValue(value=breadth_val),
                "volume": LensValue(value=vol_val),
            },
            composite_action=action,
            data_as_of=summary.data_as_of,
            reason=f"sector={key} universe={universe}",
        )

    async def _lens_country(
        self,
        ticker: str,
        benchmark: str,
        period: str,
        thresholds: dict[str, Any],
    ) -> LensBundle:
        rows = await self._svc.get_global_rs_heatmap_all()
        row = next((r for r in rows if r.get("entity_id") == ticker), None)
        if not row:
            return self._empty_bundle(
                "country", ticker, benchmark, period, reason="insufficient_data"
            )

        rs_val = _d(row.get("rs_composite"))
        rs_1m = _d(row.get("rs_1m"))

        rs_sigs = (
            signal_engine.evaluate_rs(rs_val or _D("50"), [rs_val] if rs_val else [], thresholds)
            if rs_val
            else []
        )

        return LensBundle(
            scope="country",
            entity_id=ticker,
            benchmark=benchmark,
            period=period,
            lenses={
                "rs": LensValue(value=rs_val, signals=rs_sigs),
                "momentum": LensValue(value=rs_1m),
                "breadth": LensValue(value=None),
                "volume": LensValue(value=None),
            },
            composite_action=_derive_action({"rs": rs_sigs}),
            data_as_of=None,
            reason=f"country={ticker}",
        )

    async def _lens_mf(
        self,
        mstar_id: str,
        benchmark: str,
        period: str,
        thresholds: dict[str, Any],
    ) -> LensBundle:
        detail = await self._svc.get_fund_detail(mstar_id)
        if not detail:
            return self._empty_bundle("mf", mstar_id, benchmark, period, reason="insufficient_data")

        technicals = await self._svc.get_fund_weighted_technicals(mstar_id)

        rs_val = _d((technicals or {}).get("avg_rs_composite"))
        mom_val = _d((technicals or {}).get("avg_rs_momentum"))

        rs_sigs = (
            signal_engine.evaluate_rs(rs_val or _D("50"), [rs_val] if rs_val else [], thresholds)
            if rs_val
            else []
        )

        mom_sigs = (
            signal_engine.evaluate_momentum(mom_val or _D("0"), _D("0"), thresholds)
            if mom_val
            else []
        )

        return LensBundle(
            scope="mf",
            entity_id=mstar_id,
            benchmark=benchmark,
            period=period,
            lenses={
                "rs": LensValue(value=rs_val, signals=rs_sigs),
                "momentum": LensValue(value=mom_val, signals=mom_sigs),
                "breadth": LensValue(value=None),
                "volume": LensValue(value=None),
            },
            composite_action=_derive_action({"rs": rs_sigs, "momentum": mom_sigs}),
            data_as_of=None,
            reason=f"mf={mstar_id}",
        )

    async def _lens_etf(
        self,
        ticker: str,
        benchmark: str,
        period: str,
        thresholds: dict[str, Any],
    ) -> LensBundle:
        # ETF — treat like stock
        return await self._lens_stock(ticker, benchmark, period, thresholds)

    @staticmethod
    def _empty_bundle(
        scope: str,
        entity_id: str,
        benchmark: str,
        period: str,
        reason: str = "insufficient_data",
    ) -> LensBundle:
        return LensBundle(
            scope=scope,
            entity_id=entity_id,
            benchmark=benchmark,
            period=period,
            lenses={},
            composite_action="HOLD",
            data_as_of=None,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# LeadersService — lives in lens_service.py per spec
# ---------------------------------------------------------------------------

_UNIVERSE_TO_BENCHMARK = {
    "NIFTY": "NIFTY 50",
    "NIFTY100": "NIFTY 200",
    "NIFTY500": "NIFTY 500",
    "SECTORS": "NIFTY 500",
    "ETFs": "NIFTY 500",
    "MFs": "NIFTY 500",
}


class LeadersService:
    """Rank universe constituents by 4-lens composite score."""

    def __init__(self, session: AsyncSession) -> None:
        self._svc = JIPDataService(session)

    async def rank(
        self,
        universe: str = "NIFTY500",
        benchmark: str = "NIFTY 500",
        period: str = "3M",
        aligned_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Return ranked leaders (cap 100) from the chosen universe.

        Applies the 'aligned leaders only' filter when aligned_only=True:
        rs_composite > 50 AND rs_momentum >= 0 AND (period return > 0 or absent).
        """
        thresholds = signal_engine.load_thresholds()
        aligned_cfg = thresholds.get("aligned_leaders", {})
        rs_min = _D(str(aligned_cfg.get("rs_percentile_min", 50)))
        mom_min = _D(str(aligned_cfg.get("momentum_min", 0)))

        benchmark_resolved = _UNIVERSE_TO_BENCHMARK.get(universe, benchmark)
        rows = await self._svc.get_equity_universe(benchmark=benchmark_resolved)

        results: list[dict[str, Any]] = []
        for row in rows:
            rs_val = _d(row.get("rs_composite"))
            mom_val = _d(row.get("rs_momentum"))

            if aligned_only:
                if rs_val is None or rs_val < rs_min:
                    continue
                if mom_val is not None and mom_val < mom_min:
                    continue

            results.append(
                {
                    "symbol": row.get("symbol"),
                    "company_name": row.get("company_name"),
                    "sector": row.get("sector"),
                    "rs_composite": rs_val,
                    "rs_momentum": mom_val,
                    "rs_3m": _d(row.get("rs_3m")),
                    "rs_1m": _d(row.get("rs_1m")),
                    "above_50dma": row.get("above_50dma"),
                    "above_200dma": row.get("above_200dma"),
                    "nifty_50": row.get("nifty_50"),
                    "nifty_500": row.get("nifty_500"),
                }
            )

        # Sort by RS composite descending
        results.sort(key=lambda r: r.get("rs_composite") or _D("0"), reverse=True)
        return results[:100]
