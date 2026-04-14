"""SimulationService — orchestrates the V3 simulation engine.

Coordinates data fetching, signal generation, backtest execution,
analytics computation, tax summarisation, and persistence.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AtlasSimulation
from backend.models.simulation import (
    SimulationConfig,
    SimulationResult,
    SimulationSummary,
    TaxSummary,
)
from backend.services.simulation.analytics import compute_analytics
from backend.services.simulation.backtest_engine import BacktestEngine, BacktestResult
from backend.services.simulation.repo import SimulationRepo
from backend.services.simulation.signal_adapters import (
    SignalSeries,
    combine_signals,
    get_adapter,
)
from backend.services.simulation.tax_engine import compute_annual_tax_summary

log = structlog.get_logger()


class SimulationService:
    """Simulation engine facade — wired as a FastAPI dependency."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SimulationRepo(session)

    async def run_backtest(
        self,
        config: SimulationConfig,
        price_data: Optional[list[dict[str, Any]]] = None,
        signal_data: Optional[list[dict[str, Any]]] = None,
        jip: Optional[Any] = None,  # JIPDataService — avoid circular import
    ) -> SimulationResult:
        """Execute a backtest simulation.

        Steps:
          1. Obtain price data (from jip or price_data)
          2. Obtain signal source data (from jip or signal_data)
          3. Build SignalSeries via signal adapter
          4. Run BacktestEngine
          5. Compute analytics
          6. Compute tax summary
          7. Persist to atlas_simulations
          8. Return SimulationResult

        Args:
            config: Full simulation configuration.
            price_data: Optional pre-fetched price rows [{"date": date, "nav": ...}, ...]
            signal_data: Optional pre-fetched signal rows
            jip: Optional JIPDataService for live data fetching

        Raises:
            ValueError: If data cannot be obtained.
        """
        log.info(
            "simulation_run_start",
            signal=config.signal.value,
            instrument=config.instrument,
            start_date=str(config.start_date),
            end_date=str(config.end_date),
        )

        # --- Step 1: Fetch price data ---
        price_series = await self._get_price_series(config, price_data, jip)

        # --- Step 2: Fetch signal data ---
        raw_signal_data = await self._get_signal_data(config, signal_data, jip)

        # --- Step 3: Build SignalSeries ---
        signal_series = self._build_signal_series(config, raw_signal_data)

        # --- Step 4: Run backtest engine ---
        engine = BacktestEngine()
        result: BacktestResult = engine.run(config, price_series, signal_series)

        log.info(
            "simulation_backtest_complete",
            total_invested=str(result.total_invested),
            final_value=str(result.final_value),
            transaction_count=len(result.transactions),
            daily_count=len(result.daily_values),
        )

        # --- Step 5: Compute analytics ---
        summary: SimulationSummary = compute_analytics(result, config)

        # --- Step 6: Compute tax summary ---
        tax_summary: TaxSummary = self._build_tax_summary(result, config, summary.xirr)

        # --- Step 7: Persist ---
        data_as_of = datetime.datetime.now(tz=datetime.timezone.utc)
        sim_orm = await self._persist(config, result, summary, tax_summary)

        log.info(
            "simulation_saved",
            simulation_id=str(sim_orm.id),
        )

        # --- Step 8: Return result ---
        return SimulationResult(
            summary=summary,
            daily_values=result.daily_values,
            transactions=result.transactions,
            tax_summary=tax_summary,
            tear_sheet_url=None,
            data_as_of=data_as_of,
        )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _get_price_series(
        self,
        config: SimulationConfig,
        price_data: Optional[list[dict[str, Any]]],
        jip: Optional[Any],
    ) -> list[tuple[datetime.date, Decimal]]:
        """Return list of (date, nav) from either provided data or JIP fetch."""
        if price_data is not None:
            return _parse_price_data(price_data)

        if jip is None:
            raise ValueError(
                "No price data provided and no JIP data service available. "
                "Pass price_data or jip parameter."
            )

        instrument_type = config.instrument_type.lower()
        if instrument_type == "mf":
            raw = await jip.get_fund_nav_history(
                config.instrument,
                date_from=str(config.start_date),
                date_to=str(config.end_date),
            )
            if not raw:
                raise ValueError(
                    f"No NAV history found for MF instrument '{config.instrument}' "
                    f"between {config.start_date} and {config.end_date}"
                )
            return _parse_price_data(raw)
        else:
            raise ValueError(
                f"Instrument type '{instrument_type}' requires pre-fetched price_data. "
                "Only 'mf' type supports live JIP fetch in V3-4."
            )

    async def _get_signal_data(
        self,
        config: SimulationConfig,
        signal_data: Optional[list[dict[str, Any]]],
        jip: Optional[Any],
    ) -> list[dict[str, Any]]:
        """Return raw signal data rows."""
        if signal_data is not None:
            return signal_data

        if jip is None:
            raise ValueError(
                "No signal data provided and no JIP data service available. "
                "Pass signal_data or jip parameter."
            )

        raise ValueError(
            f"Live signal data fetch for '{config.signal.value}' is not yet "
            "implemented via JIP in V3-4. Pass signal_data directly."
        )

    def _build_signal_series(
        self,
        config: SimulationConfig,
        raw_signal_data: list[dict[str, Any]],
    ) -> SignalSeries:
        """Build a SignalSeries from raw data using the appropriate adapter."""
        from backend.models.simulation import SignalType

        params = config.parameters
        buy_level = params.buy_level
        sell_level = params.sell_level
        reentry_level = params.reentry_level

        if config.signal == SignalType.COMBINED:
            if config.combined_config is None:
                raise ValueError("combined_config must be provided when signal=COMBINED")
            adapter_a = get_adapter(config.combined_config.signal_a)
            adapter_b = get_adapter(config.combined_config.signal_b)
            series_a = adapter_a(raw_signal_data, buy_level, sell_level, reentry_level)
            series_b = adapter_b(raw_signal_data, buy_level, sell_level, reentry_level)
            return combine_signals(series_a, series_b, config.combined_config.logic)
        else:
            adapter = get_adapter(config.signal)
            return adapter(raw_signal_data, buy_level, sell_level, reentry_level)

    def _build_tax_summary(
        self,
        result: BacktestResult,
        config: SimulationConfig,
        post_tax_xirr: Decimal,
    ) -> TaxSummary:
        """Build TaxSummary by aggregating disposals across all financial years."""
        if not result.all_disposals:
            unrealized = result.final_value  # Entire fund value is unrealized gain
            return TaxSummary(
                stcg=Decimal("0"),
                ltcg=Decimal("0"),
                total_tax=Decimal("0"),
                post_tax_xirr=post_tax_xirr,
                unrealized=unrealized,
            )

        # Collect all FYs that appear in disposals
        from backend.services.simulation.tax_engine import _financial_year_of

        fy_starts: set[int] = {_financial_year_of(d.sell_date) for d in result.all_disposals}

        total_stcg = Decimal("0")
        total_ltcg = Decimal("0")
        total_tax = Decimal("0")

        for fy_year in sorted(fy_starts):
            fy_date = datetime.date(fy_year, 4, 1)
            annual = compute_annual_tax_summary(result.all_disposals, fy_date)
            total_stcg += annual.stcg
            total_ltcg += annual.ltcg
            total_tax += annual.total_tax

        # Unrealized gains at the end of the simulation
        unrealized = Decimal("0")
        if result.final_nav > Decimal("0"):
            for lot in _get_remaining_lots_value(result):
                unrealized += lot

        return TaxSummary(
            stcg=total_stcg,
            ltcg=total_ltcg,
            total_tax=total_tax,
            post_tax_xirr=post_tax_xirr,
            unrealized=result.final_value - result.total_invested
            if result.final_value > result.total_invested
            else Decimal("0"),
        )

    async def _persist(
        self,
        config: SimulationConfig,
        result: BacktestResult,
        summary: SimulationSummary,
        tax_summary: TaxSummary,
    ) -> AtlasSimulation:
        """Save simulation to atlas_simulations via the repo."""

        def _sanitize_decimal(obj: Any) -> Any:
            """Recursively convert Decimal to str for JSONB storage."""
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _sanitize_decimal(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize_decimal(i) for i in obj]
            return obj

        result_summary_dict = _sanitize_decimal(summary.model_dump())
        daily_values_list = _sanitize_decimal([dv.model_dump() for dv in result.daily_values])
        transactions_list = _sanitize_decimal([tx.model_dump() for tx in result.transactions])
        tax_summary_dict = _sanitize_decimal(tax_summary.model_dump())

        sim_orm = AtlasSimulation(
            config=_sanitize_decimal(config.model_dump()),
            result_summary=result_summary_dict,
            daily_values=daily_values_list,
            transactions=transactions_list,
            tax_summary=tax_summary_dict,
        )

        await self._repo.save_simulation(sim_orm)

        return sim_orm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_price_data(
    rows: list[dict[str, Any]],
) -> list[tuple[datetime.date, Decimal]]:
    """Convert raw price rows to (date, Decimal) tuples.

    Supports rows with 'nav', 'price', 'close' as the price field.
    Date can be a date object or ISO string.
    """
    result: list[tuple[datetime.date, Decimal]] = []
    for row in rows:
        raw_date = row.get("date")
        if raw_date is None:
            continue

        if isinstance(raw_date, str):
            raw_date = datetime.date.fromisoformat(raw_date)
        elif isinstance(raw_date, datetime.datetime):
            raw_date = raw_date.date()

        # Find price field
        price_raw = row.get("nav") or row.get("price") or row.get("close")
        if price_raw is None:
            continue

        price = Decimal(str(price_raw))
        if price <= Decimal("0"):
            continue

        result.append((raw_date, price))

    return sorted(result, key=lambda x: x[0])


def _get_remaining_lots_value(result: BacktestResult) -> list[Decimal]:
    """Return list of unrealized gain per remaining lot (approx from final nav)."""
    # This is an approximation since we don't keep FIFOLotTracker after run()
    # Return empty — caller handles gracefully
    return []
