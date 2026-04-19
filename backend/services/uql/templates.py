"""UQL named templates — ``REGISTRY`` of param-validating builders.

Each builder validates its params (raising ``UQLError(TEMPLATE_PARAM_MISSING)``
on missing required) and returns a fully-formed ``UQLRequest``. Adding a
new template is a single edit to this file: define the builder, register
it in ``REGISTRY``. No other module references template names — the
engine dispatches generically via ``REGISTRY[name]``. Wired in
V2-UQL-AGG-11 per ``specs/004-uql-aggregations/tasks.md``.
"""

from __future__ import annotations

from typing import Any, Callable, Final, cast

from backend.models.schemas import (
    SortDirection,
    UQLAggregation,
    UQLEntityType,
    UQLFilter,
    UQLOperator,
    UQLRequest,
    UQLSort,
)
from backend.services.uql.errors import (
    TEMPLATE_NOT_FOUND,
    TEMPLATE_PARAM_MISSING,
    UQLError,
)

TemplateBuilder = Callable[[dict[str, Any]], UQLRequest]

_VALID_RS_PERIODS: Final[frozenset[str]] = frozenset(
    {"rs_composite", "rs_1w", "rs_1m", "rs_3m", "rs_6m", "rs_12m"}
)


def _require(params: dict[str, Any], key: str, template: str) -> Any:
    if key not in params or params[key] is None:
        raise UQLError(
            code=TEMPLATE_PARAM_MISSING,
            message=f"Template '{template}' requires parameter '{key}'",
            suggestion=f"Pass '{key}' in the template params object",
        )
    return params[key]


def _optional(params: dict[str, Any], key: str, default: Any) -> Any:
    value = params.get(key)
    return default if value is None else value


def _top_rs_gainers(params: dict[str, Any]) -> UQLRequest:
    """Top-N equities sorted by an RS field (composite or window-period).

    Optional params: ``period`` ∈ ``rs_composite|rs_1w|rs_1m|rs_3m|rs_6m|rs_12m``
    (default ``rs_composite``), ``limit`` (default 20, capped by
    UQLRequest's ``le=500``).
    """

    period = _optional(params, "period", "rs_composite")
    if period not in _VALID_RS_PERIODS:
        raise UQLError(
            code=TEMPLATE_PARAM_MISSING,
            message=(
                f"Template 'top_rs_gainers' parameter 'period' must be one of "
                f"{sorted(_VALID_RS_PERIODS)}, got {period!r}"
            ),
            suggestion="Use one of the listed RS field names as 'period'",
        )
    limit = int(_optional(params, "limit", 20))
    return UQLRequest(
        entity_type="equity",
        filters=[
            UQLFilter(field="is_active", op=UQLOperator.EQ, value=True),
            UQLFilter(field=period, op=UQLOperator.IS_NOT_NULL),
        ],
        sort=[UQLSort(field=period, direction=SortDirection.DESC)],
        fields=["symbol", "company_name", "sector", "rs_composite", period]
        if period != "rs_composite"
        else ["symbol", "company_name", "sector", "rs_composite"],
        limit=limit,
    )


def _sector_rotation(params: dict[str, Any]) -> UQLRequest:
    """Sector rollup of average RS + breadth above 50DMA.

    No required params. Optional ``limit`` (default 30).
    Returns sector_id, rs, pct_above_50dma, constituents fields.
    rs_gold and conviction are tracked separately (not in UQL entity for sector).
    """

    limit = int(_optional(params, "limit", 30))
    return UQLRequest(
        entity_type="sector",
        group_by=["sector"],
        aggregations=[
            UQLAggregation(field="rs_composite", function="avg", alias="avg_rs"),
            UQLAggregation(field="above_50dma", function="pct_true", alias="pct_above_50dma"),
            UQLAggregation(field=None, function="count_all", alias="constituents"),
        ],
        sort=[UQLSort(field="avg_rs", direction=SortDirection.DESC)],
        fields=["sector_id", "rs"],
        limit=limit,
    )


def _oversold_candidates(params: dict[str, Any]) -> UQLRequest:
    """Equities with RSI(14) below a cutoff, sorted by RS composite.

    Optional params: ``rsi_max`` (default 30), ``limit`` (default 20).
    """

    rsi_max = _optional(params, "rsi_max", 30)
    limit = int(_optional(params, "limit", 20))
    return UQLRequest(
        entity_type="equity",
        filters=[
            UQLFilter(field="is_active", op=UQLOperator.EQ, value=True),
            UQLFilter(field="rsi_14", op=UQLOperator.LT, value=rsi_max),
        ],
        sort=[UQLSort(field="rs_composite", direction=SortDirection.DESC)],
        fields=["symbol", "company_name", "sector", "rs_composite", "rsi_14", "close"],
        limit=limit,
    )


def _breadth_dashboard(params: dict[str, Any]) -> UQLRequest:
    """Per-sector breadth: pct above 50DMA, pct above 200DMA, avg RS.

    No required params. Optional ``limit`` (default 30).
    """

    limit = int(_optional(params, "limit", 30))
    return UQLRequest(
        entity_type="sector",
        group_by=["sector"],
        aggregations=[
            UQLAggregation(field="above_50dma", function="pct_true", alias="pct_above_50dma"),
            UQLAggregation(field="above_200dma", function="pct_true", alias="pct_above_200dma"),
            UQLAggregation(field="rs_composite", function="avg", alias="avg_rs"),
        ],
        sort=[UQLSort(field="pct_above_50dma", direction=SortDirection.DESC)],
        limit=limit,
    )


def _top_rs_losers(params: dict[str, Any]) -> UQLRequest:
    """Bottom-N equities sorted by RS field ascending (worst RS first).

    Optional params: ``period`` ∈ ``rs_composite|rs_1w|rs_1m|rs_3m|rs_6m|rs_12m``
    (default ``rs_composite``), ``limit`` (default 20).
    """

    period = _optional(params, "period", "rs_composite")
    if period not in _VALID_RS_PERIODS:
        raise UQLError(
            code=TEMPLATE_PARAM_MISSING,
            message=(
                f"Template 'top_rs_losers' parameter 'period' must be one of "
                f"{sorted(_VALID_RS_PERIODS)}, got {period!r}"
            ),
            suggestion="Use one of the listed RS field names as 'period'",
        )
    limit = int(_optional(params, "limit", 20))
    return UQLRequest(
        entity_type="equity",
        filters=[
            UQLFilter(field="is_active", op=UQLOperator.EQ, value=True),
            UQLFilter(field=period, op=UQLOperator.IS_NOT_NULL),
        ],
        sort=[UQLSort(field=period, direction=SortDirection.ASC)],
        fields=["symbol", "company_name", "sector", "rs_composite", period]
        if period != "rs_composite"
        else ["symbol", "company_name", "sector", "rs_composite"],
        limit=limit,
    )


def _fund_1d_movers(params: dict[str, Any]) -> UQLRequest:
    """Top MF funds sorted by 1-day return descending.

    Optional params: ``limit`` (default 20).
    """
    limit = int(_optional(params, "limit", 20))
    return UQLRequest(
        entity_type="mf",
        filters=[
            UQLFilter(field="is_active", op=UQLOperator.EQ, value=True),
        ],
        sort=[UQLSort(field="return_1d", direction=SortDirection.DESC)],
        fields=["mstar_id", "name", "category", "return_1d", "nav"],
        limit=limit,
    )


def _mf_rank_composite(params: dict[str, Any]) -> UQLRequest:
    """MF funds ranked by 4-factor composite score descending.

    Optional params: ``limit`` (default 200).
    """
    limit = int(_optional(params, "limit", 200))
    return UQLRequest(
        entity_type="mf",
        filters=[
            UQLFilter(field="is_active", op=UQLOperator.EQ, value=True),
        ],
        sort=[UQLSort(field="composite_score", direction=SortDirection.DESC)],
        fields=[
            "mstar_id",
            "name",
            "category",
            "composite_score",
            "return_score",
            "risk_score",
            "resilience_score",
            "consistency_score",
        ],
        limit=limit,
    )


def _mf_rank_history(params: dict[str, Any]) -> UQLRequest:
    """MF rank history for a set of fund IDs.

    Required params: ``mstar_ids`` (comma-separated string or list).
    Optional params: ``limit`` (default 500).
    """
    raw_ids = _require(params, "mstar_ids", "mf_rank_history")
    if isinstance(raw_ids, str):
        mstar_ids: list[str] = [i.strip() for i in raw_ids.split(",") if i.strip()]
    else:
        mstar_ids = list(raw_ids)

    limit = int(_optional(params, "limit", 500))
    return UQLRequest(
        entity_type=cast(UQLEntityType, "mf_rank_history"),
        filters=[
            UQLFilter(field="mstar_id", op=UQLOperator.IN, value=mstar_ids),
        ],
        sort=[UQLSort(field="date", direction=SortDirection.ASC)],
        fields=["mstar_id", "date", "composite_score", "rank"],
        limit=limit,
    )


REGISTRY: Final[dict[str, TemplateBuilder]] = {
    "top_rs_gainers": _top_rs_gainers,
    "top_rs_losers": _top_rs_losers,
    "sector_rotation": _sector_rotation,
    "oversold_candidates": _oversold_candidates,
    "breadth_dashboard": _breadth_dashboard,
    "fund_1d_movers": _fund_1d_movers,
    "mf_rank_composite": _mf_rank_composite,
    "mf_rank_history": _mf_rank_history,
}


def get_template(name: str) -> TemplateBuilder:
    """Look up a template builder by name.

    Raises ``UQLError(TEMPLATE_NOT_FOUND, http_status=404)`` with a
    suggestion enumerating the valid names.
    """

    try:
        return REGISTRY[name]
    except KeyError:
        valid = ", ".join(sorted(REGISTRY))
        raise UQLError(
            code=TEMPLATE_NOT_FOUND,
            message=f"Unknown UQL template '{name}'",
            suggestion=f"Valid templates: {valid}",
        ) from None


__all__ = ["REGISTRY", "TemplateBuilder", "get_template"]
