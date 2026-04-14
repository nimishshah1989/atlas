"""Unit tests for backend/services/portfolio/cams_import.py.

Tests cover:
- Decimal conversion from floats (never store float from casparser)
- Error handling for corrupt/empty files
- Holdings extraction from parsed CAS data
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from backend.services.portfolio.cams_import import (
    CamsImportError,
    CamsParseResult,
    _to_decimal,
    _to_decimal_or_none,
    parse_cas_pdf,
)


# ---------------------------------------------------------------------------
# Unit tests for Decimal helpers
# ---------------------------------------------------------------------------


def test_to_decimal_from_float_preserves_value() -> None:
    """_to_decimal converts float to Decimal via string — no float imprecision."""
    result = _to_decimal(123.456)
    assert isinstance(result, Decimal)
    assert result == Decimal("123.456")


def test_to_decimal_from_none_returns_zero() -> None:
    """_to_decimal returns Decimal('0') for None input."""
    result = _to_decimal(None)
    assert result == Decimal("0")
    assert isinstance(result, Decimal)


def test_to_decimal_from_string() -> None:
    """_to_decimal handles string numeric input."""
    result = _to_decimal("98765.4321")
    assert result == Decimal("98765.4321")


def test_to_decimal_or_none_from_none_returns_none() -> None:
    """_to_decimal_or_none returns None for None input."""
    result = _to_decimal_or_none(None)
    assert result is None


def test_to_decimal_or_none_from_float_returns_decimal() -> None:
    """_to_decimal_or_none converts floats to Decimal."""
    result = _to_decimal_or_none(49.99)
    assert isinstance(result, Decimal)
    assert result == Decimal("49.99")


def test_to_decimal_or_none_from_invalid_returns_none() -> None:
    """_to_decimal_or_none returns None for non-numeric values."""
    result = _to_decimal_or_none("not-a-number")
    assert result is None


# ---------------------------------------------------------------------------
# parse_cas_pdf — error handling
# ---------------------------------------------------------------------------


def test_parse_cas_pdf_empty_bytes_raises_error() -> None:
    """Empty bytes raises CamsImportError."""
    # We patch casparser to simulate it raising on empty input
    with patch("backend.services.portfolio.cams_import.casparser") as mock_casparser:
        mock_casparser.read_cas_pdf.side_effect = ValueError("Empty PDF")
        with pytest.raises(CamsImportError, match="Failed to parse"):
            parse_cas_pdf(b"", password=None)


def test_parse_cas_pdf_corrupt_file_raises_error() -> None:
    """Corrupt file raises CamsImportError with meaningful message."""
    with patch("backend.services.portfolio.cams_import.casparser") as mock_casparser:
        mock_casparser.read_cas_pdf.side_effect = OSError("Invalid PDF structure")
        with pytest.raises(CamsImportError, match="Failed to parse CAS PDF"):
            parse_cas_pdf(b"not a pdf", password=None)


def test_parse_cas_pdf_returns_none_raises_error() -> None:
    """casparser returning None raises CamsImportError."""
    with patch("backend.services.portfolio.cams_import.casparser") as mock_casparser:
        mock_casparser.read_cas_pdf.return_value = None
        with pytest.raises(CamsImportError, match="no data"):
            parse_cas_pdf(b"%PDF fake", password=None)


# ---------------------------------------------------------------------------
# parse_cas_pdf — successful parse
# ---------------------------------------------------------------------------


def _make_fake_cas_data(
    folios: list[dict],
    investor_name: str = "Test Investor",
    pan: str = "ABCDE1234F",
) -> MagicMock:
    """Build a fake casparser CASData object."""
    cas_data = MagicMock()

    investor_info = MagicMock()
    investor_info.name = investor_name
    investor_info.pan = pan
    cas_data.investor_info = investor_info

    folio_mocks = []
    for folio_dict in folios:
        folio_mock = MagicMock()
        folio_mock.folio = folio_dict["folio"]
        scheme_mocks = []
        for s in folio_dict["schemes"]:
            scheme_mock = MagicMock()
            scheme_mock.scheme = s["scheme"]
            scheme_mock.close = s.get("close")
            scheme_mock.balance = s.get("balance")

            valuation_mock = MagicMock()
            valuation_mock.nav = s.get("nav")
            valuation_mock.value = s.get("value")
            scheme_mock.valuation = valuation_mock

            scheme_mocks.append(scheme_mock)

        folio_mock.schemes = scheme_mocks
        folio_mocks.append(folio_mock)

    cas_data.folios = folio_mocks
    return cas_data


def test_parse_cas_pdf_extracts_holdings() -> None:
    """parse_cas_pdf returns correct holdings from mocked casparser."""
    fake_cas = _make_fake_cas_data(
        folios=[
            {
                "folio": "12345678 / 01",
                "schemes": [
                    {
                        "scheme": "Axis Bluechip Fund - Growth",
                        "close": 150.234,
                        "nav": 49.23,
                        "value": 7395.45,
                    },
                    {
                        "scheme": "Mirae Asset Large Cap Fund - Regular Plan",
                        "close": 200.0,
                        "nav": 85.10,
                        "value": 17020.0,
                    },
                ],
            }
        ]
    )

    with patch("backend.services.portfolio.cams_import.casparser") as mock_casparser:
        mock_casparser.read_cas_pdf.return_value = fake_cas

        result = parse_cas_pdf(b"%PDF fake content", password=None)

    assert isinstance(result, CamsParseResult)
    assert len(result.holdings) == 2
    assert result.investor_name == "Test Investor"
    assert result.pan == "ABCDE1234F"
    assert result.raw_folio_count == 1


def test_parse_cas_pdf_all_money_values_are_decimal() -> None:
    """All money values in parsed holdings are Decimal, never float."""
    fake_cas = _make_fake_cas_data(
        folios=[
            {
                "folio": "99999 / 01",
                "schemes": [
                    {
                        "scheme": "HDFC Mid-Cap Opportunities Fund - Growth",
                        "close": 500.1234,  # float from casparser
                        "nav": 73.45,  # float from casparser
                        "value": 36725.0,
                    },
                ],
            }
        ]
    )

    with patch("backend.services.portfolio.cams_import.casparser") as mock_casparser:
        mock_casparser.read_cas_pdf.return_value = fake_cas

        result = parse_cas_pdf(b"%PDF fake", password=None)

    holding = result.holdings[0]
    assert isinstance(holding.units, Decimal), f"units must be Decimal, got {type(holding.units)}"
    assert isinstance(holding.nav, Decimal), f"nav must be Decimal, got {type(holding.nav)}"
    assert isinstance(holding.value, Decimal), f"value must be Decimal, got {type(holding.value)}"
    # Verify exact values — no float rounding errors
    assert holding.units == Decimal("500.1234")
    assert holding.nav == Decimal("73.45")


def test_parse_cas_pdf_none_nav_stored_as_none() -> None:
    """Holdings with null NAV store None, not 0 or NaN."""
    fake_cas = _make_fake_cas_data(
        folios=[
            {
                "folio": "11111 / 01",
                "schemes": [
                    {
                        "scheme": "SBI Magnum Tax Gain Scheme - Growth",
                        "close": 100.0,
                        "nav": None,
                        "value": None,
                    },
                ],
            }
        ]
    )

    with patch("backend.services.portfolio.cams_import.casparser") as mock_casparser:
        mock_casparser.read_cas_pdf.return_value = fake_cas

        result = parse_cas_pdf(b"%PDF fake", password=None)

    holding = result.holdings[0]
    assert holding.nav is None, "None NAV must remain None, not 0"
    assert holding.value is None, "None value must remain None, not 0"


def test_parse_cas_pdf_empty_scheme_name_skipped() -> None:
    """Holdings with empty scheme names are skipped."""
    fake_cas = _make_fake_cas_data(
        folios=[
            {
                "folio": "22222 / 01",
                "schemes": [
                    {
                        "scheme": "",  # empty name — should be skipped
                        "close": 50.0,
                        "nav": 20.0,
                        "value": 1000.0,
                    },
                    {
                        "scheme": "Valid Fund Name - Growth",
                        "close": 100.0,
                        "nav": 50.0,
                        "value": 5000.0,
                    },
                ],
            }
        ]
    )

    with patch("backend.services.portfolio.cams_import.casparser") as mock_casparser:
        mock_casparser.read_cas_pdf.return_value = fake_cas

        result = parse_cas_pdf(b"%PDF fake", password=None)

    # Only the valid holding should be returned
    assert len(result.holdings) == 1
    assert result.holdings[0].scheme_name == "Valid Fund Name - Growth"


def test_parse_cas_pdf_with_password_forwards_it() -> None:
    """PDF passphrase is forwarded to casparser.read_cas_pdf."""
    fake_cas = _make_fake_cas_data(folios=[])

    with patch("backend.services.portfolio.cams_import.casparser") as mock_casparser:
        mock_casparser.read_cas_pdf.return_value = fake_cas

        pdf_pass = "abc123"
        parse_cas_pdf(b"%PDF fake", password=pdf_pass)

        call_kwargs = mock_casparser.read_cas_pdf.call_args
        assert call_kwargs is not None
        # password should be in kwargs
        _, kwargs = call_kwargs
        assert kwargs.get("password") == pdf_pass


def test_parse_cas_pdf_folio_number_stripped() -> None:
    """Folio numbers have leading/trailing whitespace stripped."""
    fake_cas = _make_fake_cas_data(
        folios=[
            {
                "folio": "  12345 / 01  ",
                "schemes": [
                    {
                        "scheme": "Test Fund - Growth",
                        "close": 100.0,
                        "nav": 50.0,
                        "value": 5000.0,
                    },
                ],
            }
        ]
    )

    with patch("backend.services.portfolio.cams_import.casparser") as mock_casparser:
        mock_casparser.read_cas_pdf.return_value = fake_cas

        result = parse_cas_pdf(b"%PDF fake", password=None)

    assert result.holdings[0].folio_number == "12345 / 01"
