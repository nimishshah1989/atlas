"""UQL v2 Pydantic schemas (spec §17 + specs/004-uql-aggregations).

Kept in its own module so ``backend/models/schemas.py`` stays under the
500-line modularity budget enforced by ``.quality/checks.py`` (check 2.4).
``backend.models.schemas`` re-exports the public names so existing imports
remain valid.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.schemas import ResponseMeta, SortDirection, UQLOperator

# Aggregation functions that require a numeric `threshold` parameter (FR-008).
# `pct_above` / `pct_below` need a cutoff; every other function rejects threshold.
_THRESHOLD_FUNCTIONS = {"pct_above", "pct_below"}

UQLAggregationFunction = Literal[
    "avg",
    "sum",
    "min",
    "max",
    "count",
    "count_all",
    "pct_true",
    "pct_positive",
    "pct_above",
    "pct_below",
    "median",
    "stddev",
]

UQLEntityType = Literal["equity", "mf", "sector", "index"]
UQLMode = Literal["snapshot", "timeseries"]
UQLGranularity = Literal["daily"]
UQLIncludeModule = Literal["identity", "rs", "technicals", "conviction"]


class UQLFilter(BaseModel):
    field: str
    op: UQLOperator
    value: Any = None


class UQLSort(BaseModel):
    field: str
    direction: SortDirection = SortDirection.DESC


class UQLAggregation(BaseModel):
    """One aggregation spec inside a UQL request (data-model §1)."""

    field: Optional[str] = None
    function: UQLAggregationFunction
    alias: str = Field(min_length=1)
    threshold: Optional[float] = None

    @model_validator(mode="after")
    def validate_aggregation(self) -> "UQLAggregation":
        if self.function != "count_all" and not self.field:
            raise ValueError(f"Aggregation function '{self.function}' requires a 'field'")
        if self.function in _THRESHOLD_FUNCTIONS and self.threshold is None:
            raise ValueError(
                f"Aggregation function '{self.function}' requires a numeric 'threshold'"
            )
        if self.function not in _THRESHOLD_FUNCTIONS and self.threshold is not None:
            raise ValueError(
                f"'threshold' is only valid for {sorted(_THRESHOLD_FUNCTIONS)}, "
                f"not '{self.function}'"
            )
        return self


class UQLTimeRange(BaseModel):
    """Inclusive date range for ``mode='timeseries'`` queries."""

    model_config = ConfigDict(populate_by_name=True)

    from_: date = Field(alias="from")
    to: date

    @model_validator(mode="after")
    def validate_range(self) -> "UQLTimeRange":
        if self.to < self.from_:
            raise ValueError("'to' must be on or after 'from'")
        return self


class UQLRequest(BaseModel):
    """UQL v2 request envelope. Mirrors specs/004-uql-aggregations contract."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "entity_type": "equity",
                    "fields": ["symbol", "company_name", "rs_composite"],
                    "filters": [{"field": "sector", "op": "=", "value": "Banking"}],
                    "sort": [{"field": "rs_composite", "direction": "desc"}],
                    "limit": 10,
                },
                {
                    "entity_type": "equity",
                    "group_by": ["sector"],
                    "aggregations": [
                        {"field": "rs_composite", "function": "avg", "alias": "avg_rs"},
                        {
                            "field": "above_200dma",
                            "function": "pct_true",
                            "alias": "pct_above_200dma",
                        },
                    ],
                    "limit": 20,
                },
                {
                    "entity_type": "equity",
                    "mode": "timeseries",
                    "filters": [{"field": "symbol", "op": "=", "value": "RELIANCE"}],
                    "fields": ["date", "close", "rs_composite"],
                    "time_range": {"from": "2026-01-01", "to": "2026-04-10"},
                    "granularity": "daily",
                    "limit": 100,
                },
            ]
        }
    )

    entity_type: UQLEntityType = "equity"
    filters: list[UQLFilter] = []
    sort: list[UQLSort] = []
    group_by: Optional[list[str]] = None
    aggregations: list[UQLAggregation] = []
    mode: UQLMode = "snapshot"
    time_range: Optional[UQLTimeRange] = None
    granularity: UQLGranularity = "daily"
    fields: Optional[list[str]] = None
    include: Optional[list[UQLIncludeModule]] = None
    limit: int = Field(default=50, le=500, ge=1)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_constraints(self) -> "UQLRequest":
        if len(self.filters) > 10:
            raise ValueError("Maximum 10 filters per query")
        if len(self.aggregations) > 8:
            raise ValueError("Maximum 8 aggregations per query")
        if self.mode == "timeseries" and self.time_range is None:
            raise ValueError("'time_range' is required when mode='timeseries'")
        if self.group_by is not None and not self.aggregations:
            raise ValueError("'aggregations' is required when 'group_by' is present")
        if self.mode == "snapshot" and self.group_by is None and not self.fields:
            raise ValueError(
                "'fields' is required for snapshot mode without group_by (spec §17.9: no SELECT *)"
            )
        if self.aggregations:
            aliases = [agg.alias for agg in self.aggregations]
            if len(aliases) != len(set(aliases)):
                raise ValueError("Aggregation aliases must be unique per request")
        return self


class UQLResponse(BaseModel):
    """Fully-shaped UQL response — records + total + provenance meta."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "records": [
                        {
                            "symbol": "HDFCBANK",
                            "company_name": "HDFC Bank",
                            "rs_composite": 82.1,
                        }
                    ],
                    "total": 1,
                    "meta": {
                        "data_as_of": "2026-04-13",
                        "query_ms": 42,
                        "returned": 1,
                        "total_count": 1,
                        "limit": 10,
                        "offset": 0,
                        "has_more": False,
                        "staleness": "fresh",
                    },
                }
            ]
        }
    )

    records: list[dict[str, Any]]
    total: int
    meta: ResponseMeta


__all__ = [
    "UQLAggregation",
    "UQLAggregationFunction",
    "UQLEntityType",
    "UQLFilter",
    "UQLGranularity",
    "UQLIncludeModule",
    "UQLMode",
    "UQLRequest",
    "UQLResponse",
    "UQLSort",
    "UQLTimeRange",
]
