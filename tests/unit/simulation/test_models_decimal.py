"""Tests that all financial fields in simulation Pydantic models are Decimal.

Regression guard for the Decimal-not-float law.
"""

from __future__ import annotations

from decimal import Decimal
from typing import get_type_hints

import pytest

from backend.models.simulation import (
    DailyValue,
    SimulationParameters,
    SimulationSummary,
    TaxDetail,
    TaxSummary,
    TransactionRecord,
)

EXPECTED_DECIMAL_FIELDS: dict[type, list[str]] = {
    SimulationSummary: [
        "total_invested",
        "final_value",
        "xirr",
        "cagr",
        "vs_plain_sip",
        "vs_benchmark",
        "alpha",
        "max_drawdown",
        "sharpe",
        "sortino",
    ],
    TaxSummary: [
        "stcg",
        "ltcg",
        "total_tax",
        "post_tax_xirr",
        "unrealized",
    ],
    TaxDetail: [
        "stcg_tax",
        "ltcg_tax",
        "cess",
        "total_tax",
    ],
    TransactionRecord: [
        "amount",
        "nav",
        "units",
    ],
    DailyValue: [
        "nav",
        "units",
        "fv",
        "liquid",
        "total",
    ],
    SimulationParameters: [
        "sip_amount",
        "lumpsum_amount",
    ],
}


@pytest.mark.parametrize(
    "model_cls,fields",
    [(cls, fields) for cls, fields in EXPECTED_DECIMAL_FIELDS.items()],
)
def test_financial_fields_are_decimal(model_cls: type, fields: list[str]) -> None:
    """Each listed financial field must be typed as Decimal."""
    hints = get_type_hints(model_cls)
    for field_name in fields:
        assert field_name in hints, f"{model_cls.__name__}.{field_name} not in type hints"
        hint = hints[field_name]
        args = getattr(hint, "__args__", ())
        is_plain = hint is Decimal
        is_optional = Decimal in args
        assert is_plain or is_optional, (
            f"{model_cls.__name__}.{field_name} must be Decimal, got {hint!r}"
        )


def test_simulation_summary_no_float_fields() -> None:
    """SimulationSummary must contain zero float-typed fields."""
    hints = get_type_hints(SimulationSummary)
    float_fields = [n for n, h in hints.items() if h is float]
    assert float_fields == [], f"Float fields found: {float_fields}"


def test_tax_summary_no_float_fields() -> None:
    """TaxSummary must contain zero float-typed fields."""
    hints = get_type_hints(TaxSummary)
    float_fields = [n for n, h in hints.items() if h is float]
    assert float_fields == [], f"Float fields found: {float_fields}"


def test_daily_value_no_float_fields() -> None:
    """DailyValue must contain zero float-typed fields."""
    hints = get_type_hints(DailyValue)
    float_fields = [n for n, h in hints.items() if h is float]
    assert float_fields == [], f"Float fields found: {float_fields}"


def test_simulation_summary_instantiation_with_decimal() -> None:
    """SimulationSummary can be instantiated with Decimal values."""
    summary = SimulationSummary(
        total_invested=Decimal("500000"),
        final_value=Decimal("750000"),
        xirr=Decimal("0.1580"),
        cagr=Decimal("0.1450"),
        vs_plain_sip=Decimal("0.0430"),
        vs_benchmark=Decimal("0.0210"),
        alpha=Decimal("0.0210"),
        max_drawdown=Decimal("-0.1850"),
        sharpe=Decimal("1.23"),
        sortino=Decimal("1.87"),
    )
    assert summary.total_invested == Decimal("500000")
    assert isinstance(summary.xirr, Decimal)
    assert isinstance(summary.max_drawdown, Decimal)
