"""Tests for V4 Portfolio Pydantic models.

Validates:
- Decimal-only financial fields (no float)
- Enum validation for PortfolioType, OwnerType, MappingStatus
- Model instantiation with correct types
- Optional field handling
"""

from __future__ import annotations

from decimal import Decimal
from typing import get_type_hints
from uuid import uuid4
import datetime

import pytest

from backend.models.portfolio import (
    HoldingBase,
    HoldingResponse,
    MappingStatus,
    OwnerType,
    PortfolioCreateRequest,
    PortfolioType,
)


# ---------------------------------------------------------------------------
# Enum validation
# ---------------------------------------------------------------------------


def test_portfolio_type_enum_values() -> None:
    """PortfolioType enum must have exactly the three spec values."""
    values = {e.value for e in PortfolioType}
    assert values == {"cams_import", "manual", "model"}


def test_owner_type_enum_values() -> None:
    """OwnerType enum must have exactly the three spec values."""
    values = {e.value for e in OwnerType}
    assert values == {"pms", "ria_client", "retail"}


def test_mapping_status_enum_values() -> None:
    """MappingStatus enum must have the three spec values."""
    values = {e.value for e in MappingStatus}
    assert values == {"mapped", "pending", "manual_override"}


# ---------------------------------------------------------------------------
# Decimal-only financial fields
# ---------------------------------------------------------------------------

FINANCIAL_FIELDS: dict[type, list[str]] = {
    HoldingBase: ["units"],
    HoldingResponse: ["units"],
}


@pytest.mark.parametrize(
    "model_cls,fields",
    [(cls, fields) for cls, fields in FINANCIAL_FIELDS.items()],
)
def test_financial_fields_are_decimal(model_cls: type, fields: list[str]) -> None:
    """Each financial field must be typed as Decimal (not float)."""
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


def test_holding_base_no_float_fields() -> None:
    """HoldingBase must contain zero float-typed fields."""
    hints = get_type_hints(HoldingBase)
    float_fields = [n for n, h in hints.items() if h is float]
    assert float_fields == [], f"Float fields found in HoldingBase: {float_fields}"


def test_holding_response_no_float_fields() -> None:
    """HoldingResponse must contain zero float-typed fields."""
    hints = get_type_hints(HoldingResponse)
    float_fields = [n for n, h in hints.items() if h is float]
    assert float_fields == [], f"Float fields found in HoldingResponse: {float_fields}"


# ---------------------------------------------------------------------------
# Model instantiation
# ---------------------------------------------------------------------------


def test_holding_base_instantiation_with_decimal() -> None:
    """HoldingBase can be instantiated with Decimal units."""
    h = HoldingBase(
        scheme_name="HDFC Flexi Cap Fund",
        units=Decimal("100.5000"),
        mapping_status=MappingStatus.pending,
    )
    assert h.units == Decimal("100.5000")
    assert isinstance(h.units, Decimal)
    assert h.mapping_status == MappingStatus.pending
    assert h.folio_number is None
    assert h.nav is None


def test_holding_base_with_all_fields() -> None:
    """HoldingBase can be instantiated with all fields including optional ones."""
    h = HoldingBase(
        scheme_name="ICICI Prudential Bluechip Fund",
        folio_number="123456/78",
        units=Decimal("250.7500"),
        nav=Decimal("88.4300"),
        mstar_id="F00000XXXX",
        mapping_confidence=Decimal("0.9500"),
        mapping_status=MappingStatus.mapped,
    )
    assert h.units == Decimal("250.7500")
    assert h.nav == Decimal("88.4300")
    assert h.mapping_confidence == Decimal("0.9500")
    assert isinstance(h.nav, Decimal)
    assert isinstance(h.mapping_confidence, Decimal)


def test_portfolio_create_request_empty_holdings() -> None:
    """PortfolioCreateRequest can be created with no holdings."""
    req = PortfolioCreateRequest(
        name="Test Portfolio",
        portfolio_type=PortfolioType.manual,
        owner_type=OwnerType.retail,
        holdings=[],
    )
    assert req.holdings == []
    assert req.portfolio_type == PortfolioType.manual
    assert req.owner_type == OwnerType.retail


def test_portfolio_create_request_with_holdings() -> None:
    """PortfolioCreateRequest can contain multiple holdings."""
    req = PortfolioCreateRequest(
        portfolio_type=PortfolioType.cams_import,
        owner_type=OwnerType.pms,
        holdings=[
            HoldingBase(
                scheme_name="Axis Midcap Fund",
                units=Decimal("500.0000"),
                mapping_status=MappingStatus.pending,
            ),
            HoldingBase(
                scheme_name="SBI Small Cap Fund",
                units=Decimal("300.0000"),
                nav=Decimal("120.5000"),
                mapping_status=MappingStatus.mapped,
                mstar_id="F00000YYYY",
            ),
        ],
    )
    assert len(req.holdings) == 2
    assert req.holdings[0].units == Decimal("500.0000")
    assert req.holdings[1].mstar_id == "F00000YYYY"


def test_portfolio_create_request_invalid_type() -> None:
    """PortfolioCreateRequest must reject invalid portfolio_type values."""
    with pytest.raises(Exception):
        PortfolioCreateRequest(
            portfolio_type="invalid_type",
            owner_type=OwnerType.retail,
            holdings=[],
        )


def test_portfolio_create_request_invalid_owner_type() -> None:
    """PortfolioCreateRequest must reject invalid owner_type values."""
    with pytest.raises(Exception):
        PortfolioCreateRequest(
            portfolio_type=PortfolioType.manual,
            owner_type="invalid_owner",
            holdings=[],
        )


def test_holding_response_from_orm_compatible() -> None:
    """HoldingResponse can be instantiated with all required DB fields."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    portfolio_id = uuid4()
    holding_id = uuid4()

    h = HoldingResponse(
        id=holding_id,
        portfolio_id=portfolio_id,
        scheme_name="Mirae Asset Emerging Bluechip",
        units=Decimal("1000.0000"),
        mapping_status=MappingStatus.pending,
        created_at=now,
        updated_at=now,
    )
    assert h.id == holding_id
    assert h.portfolio_id == portfolio_id
    assert h.current_value is None
    assert h.cost_value is None
