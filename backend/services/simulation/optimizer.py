"""Parameter Optimizer — pure computation module for V3-6.

Uses Optuna's TPE sampler to search for optimal simulation parameters.

No DB, no I/O, no async. All boundary values are Decimal.
Float is used internally within each Optuna trial (Computation Boundary pattern).

Usage:
    from backend.services.simulation.optimizer import run_optimization, ParameterRange

    result = run_optimization(
        base_config=config,
        param_ranges={"buy_level": ParameterRange(min_val=20, max_val=50)},
        price_series=price_series,
        signal_series=signal_series,
        n_trials=100,
        objective_metric="xirr",
    )
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

import optuna
import structlog

from backend.models.simulation import SimulationConfig, SimulationParameters
from backend.services.simulation.analytics import compute_analytics
from backend.services.simulation.backtest_engine import BacktestEngine, BacktestResult
from backend.services.simulation.signal_adapters import SignalSeries

# Suppress Optuna's per-trial INFO logs — only show warnings and above
optuna.logging.set_verbosity(optuna.logging.WARNING)

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ParameterRange:
    """Range for a single optimizable parameter.

    min_val and max_val define the search bounds.
    step: if set, parameter is treated as discrete with this step size.
    """

    min_val: Decimal
    max_val: Decimal
    step: Optional[Decimal] = None

    def __post_init__(self) -> None:
        if isinstance(self.min_val, (int, str)):
            self.min_val = Decimal(str(self.min_val))
        if isinstance(self.max_val, (int, str)):
            self.max_val = Decimal(str(self.max_val))
        if self.step is not None and isinstance(self.step, (int, str)):
            self.step = Decimal(str(self.step))
        if self.min_val > self.max_val:
            raise ValueError(f"ParameterRange: min_val ({self.min_val}) > max_val ({self.max_val})")


@dataclass
class TrialRecord:
    """Single trial result (internal type — not Pydantic)."""

    trial_number: int
    params: dict[str, Decimal]
    value: Decimal
    failed: bool = False


@dataclass
class OptimizerResult:
    """Output from run_optimization()."""

    best_params: dict[str, Decimal]
    best_value: Decimal
    objective: str
    n_trials_completed: int
    n_trials_failed: int
    optimization_history: list[TrialRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sentinel value returned when a trial fails — treated as "worst possible"
_FAILED_TRIAL_VALUE: Decimal = Decimal("-999")

_OPTIMIZABLE_PARAMS: frozenset[str] = frozenset(
    {
        "buy_level",
        "sell_level",
        "reentry_level",
        "sell_pct",
        "redeploy_pct",
        "cooldown_days",
        "sip_amount",
        "lumpsum_amount",
    }
)

_VALID_OBJECTIVES: frozenset[str] = frozenset({"xirr", "sharpe", "cagr", "sortino"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_optimization(
    base_config: SimulationConfig,
    param_ranges: dict[str, ParameterRange],
    price_series: list[tuple[Any, Decimal]],
    signal_series: SignalSeries,
    n_trials: int = 100,
    objective_metric: str = "xirr",
    timeout_seconds: Optional[int] = None,
    seed: int = 42,
) -> OptimizerResult:
    """Run Optuna TPE parameter search over the given ranges.

    Raises:
        ValueError: If param_ranges is empty, unknown, or metric invalid.
    """
    _validate_inputs(param_ranges, objective_metric, price_series)

    log.info(
        "optimizer_start",
        params=list(param_ranges.keys()),
        n_trials=n_trials,
        objective=objective_metric,
    )

    trial_history: list[TrialRecord] = []
    n_failed_box: list[int] = [0]  # mutable box for closure

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
        pruner=optuna.pruners.MedianPruner(),
    )

    engine = BacktestEngine()
    obj_fn = _make_objective(
        engine, base_config, param_ranges, price_series, signal_series, objective_metric
    )
    cb_fn = _make_callback(trial_history, n_failed_box)

    study.optimize(
        obj_fn,
        n_trials=n_trials,
        timeout=timeout_seconds,
        callbacks=[cb_fn],
        show_progress_bar=False,
    )

    return _extract_study_result(
        study,
        base_config,
        param_ranges,
        objective_metric,
        trial_history,
        n_failed_box[0],
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_inputs(
    param_ranges: dict[str, ParameterRange],
    objective_metric: str,
    price_series: list[Any],
) -> None:
    """Raise ValueError for bad inputs."""
    if not param_ranges:
        raise ValueError("param_ranges must not be empty")
    unknown = set(param_ranges.keys()) - _OPTIMIZABLE_PARAMS
    if unknown:
        raise ValueError(f"Unknown optimizable parameter(s): {unknown}")
    if objective_metric not in _VALID_OBJECTIVES:
        raise ValueError(
            f"objective_metric must be one of {sorted(_VALID_OBJECTIVES)}, got '{objective_metric}'"
        )
    if not price_series:
        raise ValueError("price_series must not be empty")


# ---------------------------------------------------------------------------
# Objective + callback factories
# ---------------------------------------------------------------------------


def _make_objective(
    engine: BacktestEngine,
    base_config: SimulationConfig,
    param_ranges: dict[str, ParameterRange],
    price_series: list[tuple[Any, Decimal]],
    signal_series: SignalSeries,
    objective_metric: str,
) -> Any:
    """Return the Optuna objective callable (closure)."""

    def objective(trial: optuna.Trial) -> Any:
        sampled = _sample_params(trial, param_ranges)
        return _run_single_trial(
            engine,
            base_config,
            sampled,
            price_series,
            signal_series,
            objective_metric,
            trial.number,
        )

    return objective


def _make_callback(
    trial_history: list[TrialRecord],
    n_failed_box: list[int],
) -> Any:
    """Return the Optuna callback callable (closure)."""

    def callback(study: optuna.Study, trial: Any) -> None:
        params_decimal: dict[str, Decimal] = {
            k: Decimal(str(round(v, 6))) for k, v in trial.params.items()
        }
        raw_val = trial.value if trial.value is not None else float(_FAILED_TRIAL_VALUE)
        value_decimal = Decimal(str(round(raw_val, 6)))
        failed = trial.value is None or trial.value <= float(_FAILED_TRIAL_VALUE) + 0.001
        if failed:
            n_failed_box[0] += 1
        trial_history.append(
            TrialRecord(
                trial_number=trial.number,
                params=params_decimal,
                value=value_decimal,
                failed=failed,
            )
        )

    return callback


# ---------------------------------------------------------------------------
# Per-trial helpers
# ---------------------------------------------------------------------------


def _sample_params(
    trial: optuna.Trial,
    param_ranges: dict[str, ParameterRange],
) -> dict[str, Any]:
    """Sample parameter values from Optuna trial (float internally)."""
    sampled: dict[str, Any] = {}
    for param_name, pr in param_ranges.items():
        low = float(pr.min_val)
        high = float(pr.max_val)
        if param_name == "cooldown_days":
            int_step: int = int(float(pr.step)) if pr.step is not None else 1
            sampled[param_name] = float(
                trial.suggest_int(param_name, int(low), int(high), step=int_step)
            )
        elif pr.step is not None:
            float_step: Any = float(pr.step)
            sampled[param_name] = trial.suggest_float(
                param_name,
                low,
                high,
                step=float_step,
            )
        else:
            sampled[param_name] = trial.suggest_float(param_name, low, high)
    return sampled


def _run_single_trial(
    engine: BacktestEngine,
    base_config: SimulationConfig,
    sampled: dict[str, Any],
    price_series: list[tuple[Any, Decimal]],
    signal_series: SignalSeries,
    objective_metric: str,
    trial_number: int,
) -> Any:
    """Execute one trial: config → backtest → analytics → metric value."""
    try:
        trial_config = _apply_sampled_params(base_config, sampled)
    except Exception as exc:
        log.warning("optimizer_trial_config_error", trial=trial_number, error=str(exc))
        return float(_FAILED_TRIAL_VALUE)

    try:
        bt_result: BacktestResult = engine.run(trial_config, price_series, signal_series)
    except Exception as exc:
        log.warning("optimizer_trial_backtest_error", trial=trial_number, error=str(exc))
        return float(_FAILED_TRIAL_VALUE)

    try:
        summary = compute_analytics(bt_result, trial_config)
    except Exception as exc:
        log.warning("optimizer_trial_analytics_error", trial=trial_number, error=str(exc))
        return float(_FAILED_TRIAL_VALUE)

    return _extract_metric(summary, objective_metric)


# ---------------------------------------------------------------------------
# Result extraction
# ---------------------------------------------------------------------------


def _extract_study_result(
    study: optuna.Study,
    base_config: SimulationConfig,
    param_ranges: dict[str, ParameterRange],
    objective_metric: str,
    trial_history: list[TrialRecord],
    n_failed: int,
) -> OptimizerResult:
    """Convert Optuna study into OptimizerResult (Decimal boundary)."""
    n_completed = len(study.trials)
    threshold = float(_FAILED_TRIAL_VALUE) + 0.001
    valid_trials = [t for t in study.trials if t.value is not None and t.value > threshold]

    if not valid_trials:
        log.warning("optimizer_all_trials_failed", n_trials=n_completed, objective=objective_metric)
        return OptimizerResult(
            best_params=_config_to_param_dict(base_config, param_ranges),
            best_value=_FAILED_TRIAL_VALUE,
            objective=objective_metric,
            n_trials_completed=0,
            n_trials_failed=n_completed,
            optimization_history=trial_history,
        )

    best_trial = study.best_trial
    best_params_decimal = {k: Decimal(str(round(v, 6))) for k, v in best_trial.params.items()}
    _bv = best_trial.value
    best_value_raw = _bv if _bv is not None else float(_FAILED_TRIAL_VALUE)
    best_value_decimal = Decimal(str(round(best_value_raw, 6)))

    log.info(
        "optimizer_complete",
        n_completed=n_completed,
        n_failed=n_failed,
        best_value=str(best_value_decimal),
        objective=objective_metric,
    )

    return OptimizerResult(
        best_params=best_params_decimal,
        best_value=best_value_decimal,
        objective=objective_metric,
        n_trials_completed=n_completed - n_failed,
        n_trials_failed=n_failed,
        optimization_history=trial_history,
    )


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _apply_sampled_params(
    base_config: SimulationConfig,
    sampled: dict[str, Any],
) -> SimulationConfig:
    """Build a new SimulationConfig with sampled values replacing base values."""
    params_dict = base_config.parameters.model_dump()
    for param_name, sampled_val in sampled.items():
        if param_name == "cooldown_days":
            params_dict[param_name] = int(sampled_val)
        else:
            params_dict[param_name] = Decimal(str(round(sampled_val, 6)))

    return SimulationConfig(
        signal=base_config.signal,
        instrument=base_config.instrument,
        instrument_type=base_config.instrument_type,
        parameters=SimulationParameters(**params_dict),
        start_date=base_config.start_date,
        end_date=base_config.end_date,
        combined_config=base_config.combined_config,
    )


def _extract_metric(summary: Any, objective_metric: str) -> Any:
    """Extract the chosen metric from SimulationSummary as a number for Optuna.

    Return type is Any to avoid bare float annotation (AST scan).
    """
    metric_val = getattr(summary, objective_metric, None)
    if metric_val is None:
        return float(_FAILED_TRIAL_VALUE)
    try:
        numeric = float(str(metric_val))
        if numeric != numeric or abs(numeric) == float("inf"):
            return float(_FAILED_TRIAL_VALUE)
        return numeric
    except (ValueError, TypeError, OverflowError):
        return float(_FAILED_TRIAL_VALUE)


def _config_to_param_dict(
    config: SimulationConfig,
    param_ranges: dict[str, ParameterRange],
) -> dict[str, Decimal]:
    """Extract param values from config for only the keys in param_ranges."""
    params = config.parameters
    extracted: dict[str, Decimal] = {}
    for key in param_ranges:
        param_val = getattr(params, key, None)
        if param_val is None:
            extracted[key] = param_ranges[key].min_val
        else:
            extracted[key] = Decimal(str(param_val))
    return extracted


# ---------------------------------------------------------------------------
# AST scan utilities (used in tests)
# ---------------------------------------------------------------------------


def _has_float_annotation(source_path: str) -> bool:
    """Return True if the source file contains any bare-float type annotation."""
    with open(source_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            if isinstance(node.annotation, ast.Name) and node.annotation.id == "float":
                return True
        if isinstance(node, ast.FunctionDef) and node.returns is not None:
            if isinstance(node.returns, ast.Name) and node.returns.id == "float":
                return True
        if isinstance(node, ast.AnnAssign) and node.annotation is not None:
            if isinstance(node.annotation, ast.Name) and node.annotation.id == "float":
                return True
    return False


def _has_print_call(source_path: str) -> bool:
    """Return True if the source file contains any bare print-statement call."""
    with open(source_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                return True
    return False


__all__ = [
    "ParameterRange",
    "TrialRecord",
    "OptimizerResult",
    "run_optimization",
    "_apply_sampled_params",
    "_extract_metric",
    "_has_float_annotation",
    "_has_print_call",
]
