"""CAMS PDF import service.

Parses a CAMS/KFintech/Karvy CAS PDF statement using casparser and returns
raw parsed holdings. All float values from casparser are immediately converted
to Decimal via Decimal(str(v)) at the parse boundary.

Raw PDFs are NEVER stored permanently (security requirement from spec §9).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import casparser
import structlog

log = structlog.get_logger()

# Confidence threshold: holdings below this go into needs_review
CONFIDENCE_THRESHOLD = Decimal("0.70")


def _to_decimal(value: Any) -> Decimal:
    """Convert any numeric value to Decimal via string, treating None/empty as zero.

    Args:
        value: numeric or string or None from casparser (never stored as-is)

    Returns:
        Decimal with exact representation
    """
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _to_decimal_or_none(value: Any) -> Optional[Decimal]:
    """Convert a numeric value to Decimal, returning None for null/missing values.

    Args:
        value: numeric or string or None from casparser (converted to Decimal immediately)

    Returns:
        Decimal or None
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


@dataclass
class ParsedHolding:
    """A single holding extracted from a CAS PDF — pre-mapping."""

    scheme_name: str
    folio_number: Optional[str]
    units: Decimal
    nav: Optional[Decimal]
    value: Optional[Decimal]


@dataclass
class CamsParseResult:
    """Result of parsing a CAS PDF."""

    holdings: list[ParsedHolding]
    investor_name: Optional[str]
    pan: Optional[str]
    raw_folio_count: int


class CamsImportError(ValueError):
    """Raised when a CAS PDF cannot be parsed."""

    pass


def _extract_scheme_holding(
    scheme: Any,
    folio_number: Optional[str],
) -> Optional[ParsedHolding]:
    """Extract a single ParsedHolding from a casparser scheme object.

    Returns None if the scheme name is empty (skip silently after logging).
    """
    scheme_name: str = getattr(scheme, "scheme", "") or ""
    if not scheme_name:
        log.warning("cams_empty_scheme_name", folio=folio_number)
        return None

    # valuation may be a valuation object or dict with nav/value
    valuation = getattr(scheme, "valuation", None)
    raw_nav: Any = None
    raw_value: Any = None

    if valuation is not None:
        if hasattr(valuation, "nav"):
            raw_nav = valuation.nav
        elif isinstance(valuation, dict):
            raw_nav = valuation.get("nav")
        if hasattr(valuation, "value"):
            raw_value = valuation.value
        elif isinstance(valuation, dict):
            raw_value = valuation.get("value")

    # units: casparser uses 'close' or 'balance' depending on version
    raw_units = getattr(scheme, "close", None) or getattr(scheme, "balance", None)

    return ParsedHolding(
        scheme_name=scheme_name.strip(),
        folio_number=(folio_number.strip() if folio_number else None),
        units=_to_decimal(raw_units),
        nav=_to_decimal_or_none(raw_nav),
        value=_to_decimal_or_none(raw_value),
    )


def _extract_folios(cas_data: Any) -> tuple[list[ParsedHolding], int]:
    """Iterate over casparser folios and extract ParsedHoldings.

    Returns (holdings, folio_count).
    Raises CamsImportError on structural data failures.
    """
    holdings: list[ParsedHolding] = []
    folio_count = 0
    try:
        for folio in cas_data.folios or []:
            folio_count += 1
            folio_number: Optional[str] = getattr(folio, "folio", None)
            for scheme in getattr(folio, "schemes", []) or []:
                parsed = _extract_scheme_holding(scheme, folio_number)
                if parsed is not None:
                    holdings.append(parsed)
    except (AttributeError, TypeError, ValueError) as exc:
        log.warning("cams_extraction_failed", error=str(exc))
        raise CamsImportError(f"Failed to extract holdings from CAS data: {exc}") from exc
    return holdings, folio_count


def parse_cas_pdf(
    file_bytes: bytes,
    password: Optional[str] = None,
) -> CamsParseResult:
    """Parse a CAS PDF and return extracted holdings.

    All numeric values from casparser are immediately converted to Decimal.
    The raw bytes are processed in-memory and never written to disk.

    Args:
        file_bytes: Raw bytes of the CAS PDF
        password: Optional PDF passphrase

    Returns:
        CamsParseResult with parsed holdings

    Raises:
        CamsImportError: If the PDF cannot be parsed or is not a valid CAS statement
    """
    file_obj = io.BytesIO(file_bytes)
    try:
        kwargs: dict[str, Any] = {}
        if password:
            kwargs["password"] = password
        cas_data = casparser.read_cas_pdf(file_obj, **kwargs)
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        log.warning("cams_parse_failed", error=str(exc))
        raise CamsImportError(f"Failed to parse CAS PDF: {exc}") from exc

    if cas_data is None:
        raise CamsImportError("CAS PDF returned no data — may be empty or unsupported format")

    holdings, folio_count = _extract_folios(cas_data)

    investor_info = getattr(cas_data, "investor_info", None)
    investor_name: Optional[str] = getattr(investor_info, "name", None) if investor_info else None
    pan: Optional[str] = getattr(investor_info, "pan", None) if investor_info else None

    log.info("cams_parse_complete", holdings=len(holdings), folios=folio_count)
    return CamsParseResult(
        holdings=holdings,
        investor_name=investor_name,
        pan=pan,
        raw_folio_count=folio_count,
    )
