"""SectorService — aggregates stock-level data into sector 4-lens summaries.

Stock-aggregation rule (slice §4.4): sector values are mean of constituent
stock values where the constituent set is narrowed by universe filter.
No sector-index data used.

MF mapping uses exact category match from mf_sector_map.yaml (no substring).
"""

from __future__ import annotations

import functools
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Sequence

import structlog
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.models.sectors import SectorSummary
from backend.services import signal_engine
from backend.services.signal_engine import Signal

log = structlog.get_logger(__name__)

_D = Decimal
_YAML_PATH = Path(__file__).parent.parent / "config" / "mf_sector_map.yaml"

_UNIVERSE_MAP = {
    "NIFTY": "NIFTY 50",
    "NIFTY100": "NIFTY 200",  # no 100 column — fall back to 200 with warning
    "NIFTY500": "NIFTY 500",
}

_VALID_UNIVERSES = frozenset(_UNIVERSE_MAP.keys())


@functools.lru_cache(maxsize=1)
def _load_mf_sector_map() -> dict[str, list[str]]:
    """Load mf_sector_map.yaml once and cache. Maps atlas_sector → [category_patterns]."""
    with open(_YAML_PATH, "r") as fh:
        parsed: dict[str, Any] = yaml.safe_load(fh)
    mapping: dict[str, list[str]] = {}
    for entry in parsed.get("sectors", []):
        key = entry.get("atlas_sector", "")
        patterns: list[str] = entry.get("mf_category_patterns", [])
        mapping[key] = patterns
    return mapping


def _d(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def _mean(values: "Sequence[Decimal | None]") -> Optional[Decimal]:
    good = [v for v in values if v is not None]
    if not good:
        return None
    return sum(good) / _D(len(good))


class SectorService:
    """Aggregate sector data from stock-level JIP data + sector mapping."""

    def __init__(self, svc: JIPDataService) -> None:
        self._svc = svc

    @classmethod
    def from_session(cls, session: AsyncSession) -> "SectorService":
        return cls(JIPDataService(session))

    async def list_sectors(self) -> list[str]:
        """Return distinct sector keys from equity universe."""
        rows = await self._svc.get_equity_universe()
        sectors = sorted({r.get("sector", "") for r in rows if r.get("sector")})
        return sectors

    async def sector_members(
        self,
        key: str,
        universe: str = "NIFTY500",
    ) -> list[dict[str, Any]]:
        """Return constituent stocks for a sector + universe."""
        if universe not in _VALID_UNIVERSES:
            raise ValueError(f"Unknown universe '{universe}'. Valid: {sorted(_VALID_UNIVERSES)}")
        if universe == "NIFTY100":
            log.warning("sector_members: NIFTY100 not a JIP benchmark column, using NIFTY 200")
        benchmark = _UNIVERSE_MAP[universe]
        return await self._svc.get_equity_universe(benchmark=benchmark, sector=key)

    async def sector_roll_up(
        self,
        key: str,
        universe: str = "NIFTY500",
    ) -> SectorSummary:
        """Compute 4-lens means for a sector from its constituent stocks."""
        if universe not in _VALID_UNIVERSES:
            raise ValueError(f"Unknown universe '{universe}'. Valid: {sorted(_VALID_UNIVERSES)}")

        stocks = await self.sector_members(key, universe=universe)

        if not stocks:
            log.warning("sector_roll_up: no stocks found", sector=key, universe=universe)
            return SectorSummary(
                key=key,
                universe=universe,
                four_lens={"rs": None, "momentum": None, "breadth": None, "volume": None},
                composite_action="HOLD",
            )

        rs_vals = [_d(s.get("rs_composite")) for s in stocks]
        mom_vals = [_d(s.get("rs_momentum")) for s in stocks]

        # Breadth proxy: % above 200dma
        above_200 = [s.get("above_200dma") for s in stocks]
        breadth_200 = [_D("100") if v else _D("0") for v in above_200 if v is not None]
        above_50 = [s.get("above_50dma") for s in stocks]
        breadth_50 = [_D("100") if v else _D("0") for v in above_50 if v is not None]

        breadth_mean = _mean([v for v in [_mean(breadth_200), _mean(breadth_50)] if v is not None])

        # Volume proxy: rel_vol mean where available
        rel_vols = [_d(s.get("rel_vol")) for s in stocks]
        vol_mean = _mean(rel_vols)

        four_lens = {
            "rs": _mean(rs_vals),
            "momentum": _mean(mom_vals),
            "breadth": breadth_mean,
            "volume": vol_mean,
        }

        # Build signals using mean values
        thresholds = signal_engine.load_thresholds()
        signals: list[Signal] = []
        rs_mean = four_lens["rs"]
        if rs_mean is not None:
            signals.extend(signal_engine.evaluate_rs(rs_mean, [rs_mean], thresholds))
        mom_mean = four_lens["momentum"]
        if mom_mean is not None:
            signals.extend(signal_engine.evaluate_momentum(mom_mean, _D("0"), thresholds))
        if breadth_mean is not None:
            signals.extend(
                signal_engine.evaluate_breadth(breadth_mean, breadth_mean, _D("50"), thresholds)
            )

        # Derive action
        str_map: dict[str, list[Signal]] = {}
        for sig in signals:
            k = sig.lens.value if sig.lens else "confirm"
            str_map.setdefault(k, []).append(sig)

        from backend.services.lens_service import _derive_action

        action = _derive_action(str_map)

        # Fetch MFs for the sector
        mfs = await self._get_mfs_for_sector(key)

        # ETFs: best-effort (empty for now — no sector-themed ETF JIP data)
        etfs: list[dict[str, Any]] = []

        # data_as_of from first stock with a date
        data_as_of = None
        for s in stocks:
            raw_date = s.get("date")
            if raw_date is not None:
                import datetime

                try:
                    data_as_of = datetime.date.fromisoformat(str(raw_date))
                    break
                except Exception:  # noqa: BLE001
                    pass

        return SectorSummary(
            key=key,
            universe=universe,
            four_lens=four_lens,
            signals=signals,
            composite_action=action,
            stocks=[
                {
                    "symbol": s.get("symbol"),
                    "company_name": s.get("company_name"),
                    "rs_composite": _d(s.get("rs_composite")),
                    "rs_momentum": _d(s.get("rs_momentum")),
                    "above_200dma": s.get("above_200dma"),
                }
                for s in stocks
            ],
            mfs=mfs,
            etfs=etfs,
            data_as_of=data_as_of,
        )

    async def _get_mfs_for_sector(self, key: str) -> list[dict[str, Any]]:
        """Return MFs matching the sector via exact category-name lookup."""
        sector_map = _load_mf_sector_map()
        patterns = sector_map.get(key, [])
        if not patterns:
            log.warning("_get_mfs_for_sector: no patterns for sector", sector=key)
            return []

        mf_universe = await self._svc.get_mf_universe()
        matched = [
            m
            for m in mf_universe
            if m.get("category_name") in patterns  # exact match, NOT substring
        ]
        return [
            {
                "mstar_id": m.get("mstar_id"),
                "scheme_name": m.get("scheme_name"),
                "category_name": m.get("category_name"),
                "aum_cr": _d(m.get("aum_cr")),
            }
            for m in matched
        ]
