"""Unit tests for backend/services/portfolio/scheme_mapper.py.

Tests cover:
- Fuzzy matching with known fund names
- Override short-circuit (punch list regression test)
- Confidence thresholds (>=0.70 mapped, <0.70 pending)
- All confidence values are Decimal throughout
- Empty input returns empty list
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.portfolio import MappingStatus
from backend.services.portfolio.scheme_mapper import (
    CONFIDENCE_THRESHOLD,
    MappedHolding,
    SchemeMapper,
    _normalize,
    _rapidfuzz_score,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


def test_normalize_collapses_whitespace() -> None:
    """_normalize lowercases and collapses whitespace."""
    assert _normalize("  Axis  Bluechip  Fund ") == "axis bluechip fund"


def test_normalize_lowercases() -> None:
    """_normalize lowercases all characters."""
    assert _normalize("HDFC Top 100 Fund") == "hdfc top 100 fund"


def test_rapidfuzz_score_returns_decimal() -> None:
    """_rapidfuzz_score always returns a Decimal in [0, 1]."""
    score = _rapidfuzz_score("Axis Bluechip Fund", "Axis Bluechip Fund Growth")
    assert isinstance(score, Decimal)
    assert Decimal("0") <= score <= Decimal("1")


def test_rapidfuzz_score_exact_match_is_high() -> None:
    """Exact same name → high score close to 1.0."""
    score = _rapidfuzz_score(
        "Mirae Asset Large Cap Fund",
        "Mirae Asset Large Cap Fund",
    )
    assert score >= Decimal("0.95")


def test_rapidfuzz_score_unrelated_names_is_low() -> None:
    """Completely different names → low score."""
    score = _rapidfuzz_score("Axis Bluechip Fund", "ZZZZZ Unrelated Name QQQQ")
    assert score < Decimal("0.50")


def test_confidence_threshold_is_decimal() -> None:
    """CONFIDENCE_THRESHOLD constant is a Decimal."""
    assert isinstance(CONFIDENCE_THRESHOLD, Decimal)
    assert CONFIDENCE_THRESHOLD == Decimal("0.70")


# ---------------------------------------------------------------------------
# SchemeMapper.map_holdings tests
# ---------------------------------------------------------------------------


def _make_mock_session(overrides: list[dict[str, Any]] | None = None) -> MagicMock:
    """Create a mock AsyncSession for SchemeMapper tests."""
    session = MagicMock()

    # Mock the execute call for overrides query
    override_rows: list[MagicMock] = []
    if overrides:
        for ov in overrides:
            row = MagicMock()
            row.scheme_name_pattern = ov["pattern"]
            row.mstar_id = ov["mstar_id"]
            row.is_deleted = False
            override_rows.append(row)

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = override_rows

    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock

    session.execute = AsyncMock(return_value=execute_result)
    return session


@pytest.mark.asyncio
async def test_map_holdings_empty_input_returns_empty() -> None:
    """Empty scheme_names input returns empty list."""
    session = _make_mock_session()
    mapper = SchemeMapper(session)
    result = await mapper.map_holdings([])
    assert result == []


@pytest.mark.asyncio
async def test_map_holdings_fuzzy_high_confidence_maps() -> None:
    """High-confidence fuzzy match → mapping_status='mapped'."""
    session = _make_mock_session(overrides=[])

    # Mock JIPMFService.get_mf_universe to return a known fund
    universe = [
        {"mstar_id": "F00000XYZ1", "fund_name": "Axis Bluechip Fund - Growth"},
    ]

    with patch(
        "backend.services.portfolio.scheme_mapper.JIPMFService.get_mf_universe",
        new_callable=AsyncMock,
        return_value=universe,
    ):
        mapper = SchemeMapper(session)
        results = await mapper.map_holdings(["Axis Bluechip Fund Growth"])

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, MappedHolding)
    assert result.mstar_id == "F00000XYZ1"
    assert result.mapping_status == MappingStatus.mapped
    assert isinstance(result.confidence, Decimal)
    assert result.confidence >= CONFIDENCE_THRESHOLD


@pytest.mark.asyncio
async def test_map_holdings_low_confidence_is_pending() -> None:
    """Low confidence match → mapping_status='pending', mstar_id=None."""
    session = _make_mock_session(overrides=[])

    # Universe has a completely unrelated fund
    universe = [
        {"mstar_id": "F00000ZZZZ", "fund_name": "ZZZZZ Unrelated Name QQQQ Fund"},
    ]

    with patch(
        "backend.services.portfolio.scheme_mapper.JIPMFService.get_mf_universe",
        new_callable=AsyncMock,
        return_value=universe,
    ):
        mapper = SchemeMapper(session)
        results = await mapper.map_holdings(["Axis Bluechip Fund Growth"])

    assert len(results) == 1
    result = results[0]
    assert result.mapping_status == MappingStatus.pending
    assert result.mstar_id is None
    assert result.confidence < CONFIDENCE_THRESHOLD


@pytest.mark.asyncio
async def test_map_holdings_override_short_circuits_fuzzy() -> None:
    """Override match short-circuits fuzzy — no JIP call needed for that scheme.

    Regression test for punch list item 3.
    """
    session = _make_mock_session(
        overrides=[
            {"pattern": "axis bluechip fund - growth", "mstar_id": "F00000OVERRIDE"},
        ]
    )

    # JIP universe should NOT be needed for the overridden scheme
    # We still need to provide it because other schemes might need it
    universe: list[dict[str, Any]] = []

    with patch(
        "backend.services.portfolio.scheme_mapper.JIPMFService.get_mf_universe",
        new_callable=AsyncMock,
        return_value=universe,
    ) as mock_universe:
        mapper = SchemeMapper(session)
        results = await mapper.map_holdings(["Axis Bluechip Fund - Growth"])

    assert len(results) == 1
    result = results[0]
    assert result.mstar_id == "F00000OVERRIDE"
    assert result.mapping_status == MappingStatus.manual_override
    assert result.confidence == Decimal("1.0")
    # JIP universe should NOT have been called since override handled it
    mock_universe.assert_not_called()


@pytest.mark.asyncio
async def test_map_holdings_override_confidence_is_decimal_one() -> None:
    """Override match always returns confidence=Decimal('1.0')."""
    session = _make_mock_session(
        overrides=[
            {"pattern": "hdfc mid-cap opportunities fund - growth", "mstar_id": "F00000HDFC"},
        ]
    )

    with patch(
        "backend.services.portfolio.scheme_mapper.JIPMFService.get_mf_universe",
        new_callable=AsyncMock,
        return_value=[],
    ):
        mapper = SchemeMapper(session)
        results = await mapper.map_holdings(["HDFC Mid-Cap Opportunities Fund - Growth"])

    result = results[0]
    assert isinstance(result.confidence, Decimal)
    assert result.confidence == Decimal("1.0")


@pytest.mark.asyncio
async def test_map_holdings_preserves_order() -> None:
    """Results are returned in the same order as input scheme names."""
    session = _make_mock_session(overrides=[])

    universe = [
        {"mstar_id": "F00000AAA", "fund_name": "Axis Bluechip Fund Growth"},
        {"mstar_id": "F00000BBB", "fund_name": "Mirae Asset Large Cap Fund"},
        {"mstar_id": "F00000CCC", "fund_name": "SBI Magnum Tax Gain Scheme"},
    ]

    scheme_names = [
        "Mirae Asset Large Cap Fund",
        "Axis Bluechip Fund Growth",
        "SBI Magnum Tax Gain Scheme",
    ]

    with patch(
        "backend.services.portfolio.scheme_mapper.JIPMFService.get_mf_universe",
        new_callable=AsyncMock,
        return_value=universe,
    ):
        mapper = SchemeMapper(session)
        results = await mapper.map_holdings(scheme_names)

    assert len(results) == 3
    assert results[0].scheme_name == scheme_names[0]
    assert results[1].scheme_name == scheme_names[1]
    assert results[2].scheme_name == scheme_names[2]


@pytest.mark.asyncio
async def test_map_holdings_confidence_always_decimal() -> None:
    """All confidence values in results are Decimal, never float."""
    session = _make_mock_session(overrides=[])

    universe = [
        {"mstar_id": "F00000XYZ", "fund_name": "Axis Bluechip Fund Growth"},
    ]

    with patch(
        "backend.services.portfolio.scheme_mapper.JIPMFService.get_mf_universe",
        new_callable=AsyncMock,
        return_value=universe,
    ):
        mapper = SchemeMapper(session)
        results = await mapper.map_holdings(["Axis Bluechip Fund Growth"])

    for r in results:
        assert isinstance(r.confidence, Decimal), (
            f"confidence must be Decimal, got {type(r.confidence)}"
        )


@pytest.mark.asyncio
async def test_map_holdings_mixed_override_and_fuzzy() -> None:
    """Mix of override and fuzzy matching works correctly together."""
    session = _make_mock_session(
        overrides=[
            {"pattern": "axis bluechip fund - growth", "mstar_id": "F00000OVERRIDE"},
        ]
    )

    universe = [
        {"mstar_id": "F00000MIRAE", "fund_name": "Mirae Asset Large Cap Fund"},
    ]

    scheme_names = [
        "Axis Bluechip Fund - Growth",  # will be overridden
        "Mirae Asset Large Cap Fund",  # will be fuzzy matched
    ]

    with patch(
        "backend.services.portfolio.scheme_mapper.JIPMFService.get_mf_universe",
        new_callable=AsyncMock,
        return_value=universe,
    ):
        mapper = SchemeMapper(session)
        results = await mapper.map_holdings(scheme_names)

    assert results[0].mstar_id == "F00000OVERRIDE"
    assert results[0].mapping_status == MappingStatus.manual_override
    assert results[1].mstar_id == "F00000MIRAE"
    assert results[1].mapping_status == MappingStatus.mapped
