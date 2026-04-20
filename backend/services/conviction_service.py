"""ConvictionService — computes weighted conviction score per instrument.

Score = w_selection * selection + w_value * value + w_regime_fit * regime_fit.
Weights are loaded from signal_thresholds.yaml conviction_weights key.
All financial values are Decimal. Degrades gracefully on missing data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.models.conviction import ConvictionScore
from backend.services import signal_engine
from backend.services.lens_service import LensService

log = structlog.get_logger(__name__)

_D = Decimal


def _d(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


class ConvictionService:
    """Compute conviction score for a stock or MF instrument."""

    def __init__(self, session: AsyncSession) -> None:
        self._svc = JIPDataService(session)
        self._lens = LensService(session)

    async def score(self, instrument_id: str, scope: str) -> ConvictionScore:
        """Return ConvictionScore for the given instrument.

        Selection sub-score: average of (rs_composite percentile 0..100) and
        (positive momentum mapped 0..100).
        Value sub-score: pe_ratio < 25 → 70; 25..40 → 50; > 40 → 20 (RICH zone).
        Regime fit: BULL→80, CAUTIOUS→60, CORRECTION→40, BEAR→20, unknown→50.
        """
        thresholds = signal_engine.load_thresholds()
        weights_cfg = thresholds.get("conviction_weights", {})
        w_sel = _D(str(weights_cfg.get("w_selection", "0.4")))
        w_val = _D(str(weights_cfg.get("w_value", "0.3")))
        w_reg = _D(str(weights_cfg.get("w_regime_fit", "0.3")))

        bands_cfg = thresholds.get("weight_bands", {})
        small_pct = _D(str(bands_cfg.get("small_pct", "1")))
        medium_pct = _D(str(bands_cfg.get("medium_pct", "3")))
        large_pct = _D(str(bands_cfg.get("large_pct", "5")))
        rich_cap = _D(str(bands_cfg.get("rich_zone_cap_pct", "1")))

        # --- selection sub-score ---
        selection, rs_val, pe_ratio_val, is_rich = await self._compute_selection(
            instrument_id, scope
        )

        # --- value sub-score ---
        value, value_reason = self._compute_value(pe_ratio_val)

        # --- regime fit sub-score ---
        regime_fit, regime_label = await self._compute_regime_fit()

        # --- weighted score ---
        raw_score = w_sel * selection + w_val * value + w_reg * regime_fit
        final_score = min(max(raw_score, _D("0")), _D("100"))

        # --- weight band derivation ---
        weight_band, suggested_pct = self._derive_weight_band(
            final_score, is_rich, small_pct, medium_pct, large_pct, rich_cap
        )

        reasons = [
            f"selection={selection:.1f}",
            f"value={value:.1f} ({value_reason})",
            f"regime_fit={regime_fit:.1f} ({regime_label})",
        ]
        if is_rich:
            reasons.append("RICH zone: weight capped at 1%")

        return ConvictionScore(
            instrument_id=instrument_id,
            scope=scope,
            score=final_score.quantize(_D("0.01")),
            weight_band=f"{int(suggested_pct)}%",
            components={
                "selection": selection.quantize(_D("0.01")),
                "value": value.quantize(_D("0.01")),
                "regime_fit": regime_fit.quantize(_D("0.01")),
            },
            suggested_weight_pct=suggested_pct,
            reason="; ".join(reasons),
        )

    async def _compute_selection(
        self, instrument_id: str, scope: str
    ) -> tuple[Decimal, Optional[Decimal], Optional[Decimal], bool]:
        """Return (selection_score, rs_val, pe_ratio_val, is_rich)."""
        try:
            bundle = await self._lens.get_lenses(
                scope=scope if scope in {"stock", "mf", "etf", "sector", "country"} else "stock",
                entity_id=instrument_id,
            )
            rs_lv = bundle.lenses.get("rs")
            mom_lv = bundle.lenses.get("momentum")
            rs_val = rs_lv.value if rs_lv else None
            mom_val = mom_lv.value if mom_lv else None
        except Exception as exc:  # noqa: BLE001
            log.warning("conviction_service: lens fetch failed", error=str(exc))
            rs_val = None
            mom_val = None

        # rs_composite is already 0-100 percentile
        rs_score = min(max(rs_val or _D("50"), _D("0")), _D("100"))

        # momentum mapped: positive→100, negative→0, zero→50
        if mom_val is not None:
            if mom_val > _D("0"):
                mom_score = _D("100")
            elif mom_val < _D("0"):
                mom_score = _D("0")
            else:
                mom_score = _D("50")
        else:
            mom_score = _D("50")

        selection = (rs_score + mom_score) / _D("2")

        # pe_ratio: stock only
        pe_ratio_val: Optional[Decimal] = None
        is_rich = False
        if scope == "stock":
            try:
                detail = await self._svc.get_stock_detail(instrument_id)
                if detail:
                    pe_ratio_val = _d(detail.get("pe_ratio"))
                    if pe_ratio_val is not None and pe_ratio_val > _D("40"):
                        is_rich = True
            except Exception as exc:  # noqa: BLE001
                log.warning("conviction_service: stock detail fetch failed", error=str(exc))
        elif scope == "mf":
            try:
                detail = await self._svc.get_fund_detail(instrument_id)
                if detail:
                    pe_ratio_val = _d(detail.get("pe_ratio"))
                    if pe_ratio_val is not None and pe_ratio_val > _D("40"):
                        is_rich = True
            except Exception as exc:  # noqa: BLE001
                log.warning("conviction_service: fund detail fetch failed", error=str(exc))

        return selection, rs_val, pe_ratio_val, is_rich

    def _compute_value(self, pe_ratio: Optional[Decimal]) -> tuple[Decimal, str]:
        """Return (value_score, reason_label)."""
        if pe_ratio is None:
            return _D("50"), "pe_absent"
        if pe_ratio < _D("25"):
            return _D("70"), f"pe={pe_ratio:.1f}<25"
        if pe_ratio <= _D("40"):
            return _D("50"), f"pe={pe_ratio:.1f} 25..40"
        # RICH zone
        return _D("20"), f"pe={pe_ratio:.1f}>40 RICH"

    async def _compute_regime_fit(self) -> tuple[Decimal, str]:
        """Return (regime_fit_score, regime_label) from latest market regime."""
        try:
            regime_data = await self._svc.get_market_regime()
            if regime_data:
                label = str(regime_data.get("regime", "")).upper()
                _map = {
                    "BULL": _D("80"),
                    "CAUTIOUS": _D("60"),
                    "CORRECTION": _D("40"),
                    "BEAR": _D("20"),
                }
                if label in _map:
                    return _map[label], label
        except Exception as exc:  # noqa: BLE001
            log.warning("conviction_service: regime fetch failed", error=str(exc))
        return _D("50"), "unknown"

    @staticmethod
    def _derive_weight_band(
        score: Decimal,
        is_rich: bool,
        small_pct: Decimal,
        medium_pct: Decimal,
        large_pct: Decimal,
        rich_cap: Decimal,
    ) -> tuple[str, Decimal]:
        """Return (band_label, suggested_weight_pct)."""
        if score >= _D("80"):
            pct = large_pct
            label = "LARGE"
        elif score >= _D("60"):
            pct = medium_pct
            label = "MEDIUM"
        elif score >= _D("40"):
            pct = small_pct
            label = "SMALL"
        else:
            return "ZERO", _D("0")

        # Apply RICH zone cap
        if is_rich and pct > rich_cap:
            pct = rich_cap
            label = "SMALL"

        return label, pct
