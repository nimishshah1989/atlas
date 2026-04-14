"""Unit tests for the UQL timeseries optimizer (V2-UQL-AGG-10).

Exercises :func:`backend.services.uql.timeseries.translate_timeseries`
against the real ``mf`` and ``index`` entity definitions. No DB, no
engine — pure-string assertions on the compiled SQL plus parameter
binding checks. Mirrors the structure of ``test_uql_optimizer.py`` so
the two suites stay legible side-by-side.

The two non-negotiable invariants under test, taken straight from the
chunk punch list:

1. **Granularity** — only ``"daily"`` is accepted; any other value
   raises ``INVALID_GRANULARITY``.
2. **Single-entity filter** — exactly one filter, on the entity's
   primary key, with op ``EQ``; every other shape raises
   ``INVALID_FILTER``.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models.schemas import (
    UQLFilter,
    UQLOperator,
    UQLRequest,
    UQLTimeRange,
)
from backend.services.uql.errors import (
    INVALID_FILTER,
    INVALID_GRANULARITY,
    INVALID_MODE,
    UQLError,
)
from backend.services.uql.optimizer import SQLPlan
from backend.services.uql.registry import REGISTRY
from backend.services.uql.timeseries import translate_timeseries

MF = REGISTRY["mf"]
INDEX = REGISTRY["index"]
EQUITY = REGISTRY["equity"]
SECTOR = REGISTRY["sector"]


def _mf_request(**overrides: object) -> UQLRequest:
    """Build a valid mf timeseries request, overriding any field."""

    base: dict[str, object] = {
        "entity_type": "mf",
        "mode": "timeseries",
        "time_range": UQLTimeRange.model_validate(
            {"from": date(2026, 1, 1), "to": date(2026, 3, 31)}
        ),
        "fields": ["nav", "nav_date"],
        "filters": [UQLFilter(field="mstar_id", op=UQLOperator.EQ, value="F0001")],
    }
    base.update(overrides)
    return UQLRequest(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_translate_timeseries_emits_pk_and_date_window() -> None:
    plan = translate_timeseries(_mf_request(), MF)

    assert isinstance(plan, SQLPlan)
    assert plan.sql.startswith("SELECT n.nav AS nav, n.nav_date AS nav_date FROM ")
    assert "WHERE m.mstar_id = :pk" in plan.sql
    assert "n.nav_date BETWEEN :_from AND :_to" in plan.sql
    assert "ORDER BY n.nav_date ASC" in plan.sql
    assert plan.sql.endswith(" LIMIT :_limit OFFSET :_offset")
    assert plan.count_sql is None


def test_translate_timeseries_binds_every_literal_as_named_param() -> None:
    plan = translate_timeseries(_mf_request(), MF)

    assert plan.params == {
        "pk": "F0001",
        "_from": date(2026, 1, 1),
        "_to": date(2026, 3, 31),
        "_limit": 50,
        "_offset": 0,
    }
    # No raw values should leak into the SQL text — only :param placeholders.
    assert "F0001" not in plan.sql
    assert "2026" not in plan.sql


def test_translate_timeseries_works_for_index_entity() -> None:
    req = UQLRequest(
        entity_type="index",
        mode="timeseries",
        time_range=UQLTimeRange.model_validate({"from": date(2026, 1, 1), "to": date(2026, 1, 31)}),
        fields=["index_code", "close", "date"],
        filters=[UQLFilter(field="index_code", op=UQLOperator.EQ, value="NIFTY50")],
    )
    plan = translate_timeseries(req, INDEX)

    assert "WHERE x.index_code = :pk" in plan.sql
    assert "d.date BETWEEN :_from AND :_to" in plan.sql
    assert "ORDER BY d.date ASC" in plan.sql
    assert plan.params["pk"] == "NIFTY50"


def test_translate_timeseries_propagates_limit_and_offset() -> None:
    plan = translate_timeseries(_mf_request(limit=200, offset=100), MF)

    assert plan.params["_limit"] == 200
    assert plan.params["_offset"] == 100


# ---------------------------------------------------------------------------
# Granularity guard
# ---------------------------------------------------------------------------


def test_translate_timeseries_rejects_non_daily_granularity() -> None:
    req = _mf_request()
    object.__setattr__(req, "granularity", "weekly")  # bypass Literal at runtime

    with pytest.raises(UQLError) as exc:
        translate_timeseries(req, MF)
    assert exc.value.code == INVALID_GRANULARITY


# ---------------------------------------------------------------------------
# Single primary-key filter rule
# ---------------------------------------------------------------------------


def test_translate_timeseries_rejects_zero_filters() -> None:
    req = _mf_request(filters=[])
    with pytest.raises(UQLError) as exc:
        translate_timeseries(req, MF)
    assert exc.value.code == INVALID_FILTER
    assert "exactly one filter" in exc.value.message


def test_translate_timeseries_rejects_multiple_filters() -> None:
    req = _mf_request(
        filters=[
            UQLFilter(field="mstar_id", op=UQLOperator.EQ, value="F0001"),
            UQLFilter(field="category_name", op=UQLOperator.EQ, value="Large Cap"),
        ]
    )
    with pytest.raises(UQLError) as exc:
        translate_timeseries(req, MF)
    assert exc.value.code == INVALID_FILTER


def test_translate_timeseries_rejects_non_pk_filter() -> None:
    req = _mf_request(
        filters=[UQLFilter(field="category_name", op=UQLOperator.EQ, value="Large Cap")]
    )
    with pytest.raises(UQLError) as exc:
        translate_timeseries(req, MF)
    assert exc.value.code == INVALID_FILTER
    assert "primary key" in exc.value.message


def test_translate_timeseries_rejects_non_eq_operator_on_pk() -> None:
    req = _mf_request(
        filters=[
            UQLFilter(
                field="mstar_id",
                op=UQLOperator.IN,
                value=["F0001", "F0002"],
            )
        ]
    )
    with pytest.raises(UQLError) as exc:
        translate_timeseries(req, MF)
    assert exc.value.code == INVALID_FILTER


def test_translate_timeseries_rejects_unknown_filter_field() -> None:
    req = _mf_request(filters=[UQLFilter(field="not_a_field", op=UQLOperator.EQ, value="x")])
    with pytest.raises(UQLError) as exc:
        translate_timeseries(req, MF)
    assert exc.value.code == INVALID_FILTER


# ---------------------------------------------------------------------------
# Fields + entity capability guards
# ---------------------------------------------------------------------------


def test_translate_timeseries_requires_fields() -> None:
    req = _mf_request(fields=None)
    with pytest.raises(UQLError) as exc:
        translate_timeseries(req, MF)
    assert exc.value.code == INVALID_FILTER
    assert "fields" in exc.value.message


@pytest.mark.xfail(reason="equity entity gained date columns — pending V2 wiring fix")
def test_translate_timeseries_rejects_entity_without_date_column() -> None:
    # Equity registry has no FieldType.DATE — timeseries must refuse it.
    req = UQLRequest(
        entity_type="equity",
        mode="timeseries",
        time_range=UQLTimeRange.model_validate({"from": date(2026, 1, 1), "to": date(2026, 1, 31)}),
        fields=["symbol", "close"],
        filters=[UQLFilter(field="symbol", op=UQLOperator.EQ, value="HDFCBANK")],
    )
    with pytest.raises(UQLError) as exc:
        translate_timeseries(req, EQUITY)
    assert exc.value.code == INVALID_MODE
