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
    AutoLoopResultItem,
    DriftThresholds,
    OptimizeResponse,
    OptimizeRequest,
    SimulationConfig,
    SimulationResult,
    SimulationSummary,
    TaxSummary,
    TrialResult,
)
from backend.services.simulation.analytics import compute_analytics
from backend.services.simulation.backtest_engine import BacktestResult
from backend.services.simulation.repo import SimulationRepo
from backend.services.simulation.signal_adapters import (
    SignalSeries,
    combine_signals,
    get_adapter,
)
from backend.services.simulation.drift_detector import detect_drift
from backend.services.simulation.helpers import (
    compute_summary_delta,
    get_remaining_lots_value,
    parse_price_data,
    sanitize_for_jsonb,
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
        engine: str = "vectorbt",
    ) -> SimulationResult:
        """Execute a backtest simulation.

        Fetches price+signal data, runs the selected engine (vectorbt or legacy),
        computes analytics + tax summary, persists to atlas_simulations, and returns
        SimulationResult.

        Args:
            config: Full simulation configuration.
            price_data: Optional pre-fetched price rows.
            signal_data: Optional pre-fetched signal rows.
            jip: Optional JIPDataService for live data fetching.
            engine: "vectorbt" (default) | "legacy" — selects the backtest engine.

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
        if engine == "legacy":
            from backend.services.simulation.backtest_engine import BacktestEngine as _LegacyEngine

            bt_result: BacktestResult = _LegacyEngine().run(config, price_series, signal_series)
        else:
            from backend.services.simulation.vectorbt_engine import VectorbtEngine as _VbtEngine

            bt_result = _VbtEngine().run(config, price_series, signal_series)

        log.info(
            "simulation_backtest_complete",
            total_invested=str(bt_result.total_invested),
            final_value=str(bt_result.final_value),
            transaction_count=len(bt_result.transactions),
            daily_count=len(bt_result.daily_values),
        )

        # --- Step 5: Compute analytics ---
        summary: SimulationSummary = compute_analytics(bt_result, config)

        # --- Step 6: Compute tax summary ---
        tax_summary: TaxSummary = self._build_tax_summary(bt_result, config, summary.xirr)

        # --- Step 7: Persist ---
        data_as_of = datetime.datetime.now(tz=datetime.timezone.utc)
        sim_orm = await self._persist(config, bt_result, summary, tax_summary)

        log.info(
            "simulation_saved",
            simulation_id=str(sim_orm.id),
        )

        # --- Step 8: Return result ---
        return SimulationResult(
            summary=summary,
            daily_values=bt_result.daily_values,
            transactions=bt_result.transactions,
            tax_summary=tax_summary,
            tear_sheet_url=None,
            data_as_of=data_as_of,
        )

    async def list_simulations(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[AtlasSimulation]:
        """Return saved simulations, newest first, excluding soft-deleted."""
        return await self._repo.list_simulations(user_id=user_id, limit=limit)

    async def get_simulation(self, sim_id: str) -> Optional[AtlasSimulation]:
        """Fetch a single simulation by UUID string, excluding soft-deleted."""
        import uuid as _uuid

        try:
            uid = _uuid.UUID(sim_id)
        except ValueError:
            return None
        return await self._repo.get_simulation(uid)

    async def save_config(
        self,
        config: SimulationConfig,
        name: Optional[str] = None,
        is_auto_loop: bool = False,
        auto_loop_cron: Optional[str] = None,
    ) -> AtlasSimulation:
        """Persist a simulation config without running the backtest.

        Used for saving auto-loop configurations that will be re-run on a schedule.
        """
        log.info(
            "simulation_save_config",
            signal=config.signal.value,
            instrument=config.instrument,
            is_auto_loop=is_auto_loop,
        )

        sim_orm = AtlasSimulation(
            name=name,
            config=sanitize_for_jsonb(config.model_dump()),
            is_auto_loop=is_auto_loop,
            auto_loop_cron=auto_loop_cron,
            result_summary=None,
            daily_values=None,
            transactions=None,
            tax_summary=None,
        )
        await self._repo.save_simulation(sim_orm)

        log.info("simulation_config_saved", simulation_id=str(sim_orm.id))
        return sim_orm

    async def delete_simulation(self, sim_id: str) -> bool:
        """Soft-delete a simulation by UUID string. Returns True if found+deleted."""
        import uuid as _uuid

        try:
            uid = _uuid.UUID(sim_id)
        except ValueError:
            return False
        return await self._repo.soft_delete(uid)

    async def run_auto_loop(self, jip: Any) -> list[AutoLoopResultItem]:
        """Re-run all active auto-loop simulations with latest data.

        Each simulation is independently locked, re-run, and updated.
        A failure on one simulation does not stop others.
        """
        active_sims = await self._repo.list_simulations(user_id=None, limit=500)
        auto_loop_sims = [s for s in active_sims if s.is_auto_loop and not s.is_deleted]

        log.info("auto_loop_start", total_candidates=len(auto_loop_sims))

        results: list[AutoLoopResultItem] = []
        for sim in auto_loop_sims:
            loop_result = await self._rerun_single_sim(sim, jip)
            results.append(loop_result)

        log.info(
            "auto_loop_complete",
            total=len(results),
            succeeded=sum(1 for r in results if r.status == "success"),
            failed=sum(1 for r in results if r.status == "error"),
        )
        return results

    async def _rerun_single_sim(
        self,
        sim: Any,
        jip: Any,
    ) -> AutoLoopResultItem:
        """Lock, re-run, and compute delta for one auto-loop simulation."""
        import uuid as _uuid

        sim_id_str = str(sim.id)
        sim_log = log.bind(simulation_id=sim_id_str)

        try:
            locked = await self._repo.lock_for_update(sim.id)
            if locked is None:
                sim_log.info("auto_loop_sim_skipped_locked")
                return AutoLoopResultItem(
                    simulation_id=sim.id,
                    status="skipped",
                    error="Could not acquire lock",
                )

            config = SimulationConfig.model_validate(locked.config or {})
            prev_summary = locked.result_summary or {}

            sim_log.info("auto_loop_sim_rerun_start", signal=config.signal.value)
            rerun_result = await self.run_backtest(config=config, jip=jip)

            delta = compute_summary_delta(rerun_result.summary, prev_summary)

            # Detect drift and store in drift_history
            drift_alerts = detect_drift(
                summary_delta=delta,
                previous_summary=prev_summary,
                thresholds=DriftThresholds(),
            )

            # Persist drift_history to DB if column exists
            if drift_alerts:
                existing_history = locked.drift_history or []
                new_event: dict[str, object] = {
                    "ran_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                    "alerts": sanitize_for_jsonb([a.model_dump() for a in drift_alerts]),
                }
                updated_history = list(existing_history) + [new_event]
                locked.drift_history = sanitize_for_jsonb(updated_history)

            needs_reoptimization = any(a.severity in ("HIGH", "CRITICAL") for a in drift_alerts)

            locked.last_auto_run = datetime.datetime.now(tz=datetime.timezone.utc)
            await self._session.flush()

            sim_log.info("auto_loop_sim_rerun_complete", xirr=str(rerun_result.summary.xirr))
            return AutoLoopResultItem(
                simulation_id=_uuid.UUID(sim_id_str),
                status="success",
                summary_delta=delta if delta else None,
                drift_alerts=drift_alerts if drift_alerts else None,
                needs_reoptimization=needs_reoptimization,
            )

        except Exception as exc:
            sim_log.error("auto_loop_sim_error", error=str(exc))
            return AutoLoopResultItem(
                simulation_id=_uuid.UUID(sim_id_str),
                status="error",
                error=str(exc),
            )

    async def optimize(
        self,
        request: OptimizeRequest,
        jip: Optional[Any] = None,
        price_data: Optional[list[dict[str, Any]]] = None,
        signal_data: Optional[list[dict[str, Any]]] = None,
    ) -> OptimizeResponse:
        """Run Optuna TPE parameter optimization.

        Fetches price + signal data once, then dispatches to run_optimization()
        for n_trials backtests. Returns best params and full trial history.
        """
        from backend.services.simulation.optimizer import ParameterRange, run_optimization

        config = request.config
        log.info("optimize_start", signal=config.signal.value, n_trials=request.n_trials)

        price_series = await self._get_price_series(config, price_data, jip)
        raw_signal_data = await self._get_signal_data(config, signal_data, jip)
        signal_series = self._build_signal_series(config, raw_signal_data)

        param_ranges_dc: dict[str, ParameterRange] = {
            name: ParameterRange(min_val=pr.min_val, max_val=pr.max_val, step=pr.step)
            for name, pr in request.param_ranges.items()
        }

        opt_result = run_optimization(
            base_config=config,
            param_ranges=param_ranges_dc,
            price_series=price_series,
            signal_series=signal_series,
            n_trials=request.n_trials,
            objective_metric=request.objective,
        )

        trial_results = [
            TrialResult(trial_number=tr.trial_number, params=tr.params, value=tr.value)
            for tr in opt_result.optimization_history
        ]
        data_as_of = datetime.datetime.now(tz=datetime.timezone.utc)
        log.info("optimize_complete", best_value=str(opt_result.best_value))

        return OptimizeResponse(
            best_params=opt_result.best_params,
            best_value=opt_result.best_value,
            objective=opt_result.objective,
            n_trials=opt_result.n_trials_completed,
            trials=trial_results,
            base_config=config,
            data_as_of=data_as_of,
        )

    async def _get_price_series(
        self,
        config: SimulationConfig,
        price_data: Optional[list[dict[str, Any]]],
        jip: Optional[Any],
    ) -> list[tuple[datetime.date, Decimal]]:
        """Return list of (date, nav) from either provided data or JIP fetch."""
        if price_data is not None:
            return parse_price_data(price_data)

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
            return parse_price_data(raw)
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
            for lot in get_remaining_lots_value(result):
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
        result_summary_dict = sanitize_for_jsonb(summary.model_dump())
        daily_values_list = sanitize_for_jsonb([dv.model_dump() for dv in result.daily_values])
        transactions_list = sanitize_for_jsonb([tx.model_dump() for tx in result.transactions])
        tax_summary_dict = sanitize_for_jsonb(tax_summary.model_dump())

        sim_orm = AtlasSimulation(
            config=sanitize_for_jsonb(config.model_dump()),
            result_summary=result_summary_dict,
            daily_values=daily_values_list,
            transactions=transactions_list,
            tax_summary=tax_summary_dict,
        )

        await self._repo.save_simulation(sim_orm)

        return sim_orm
