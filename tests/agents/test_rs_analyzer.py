"""Unit tests for backend/agents/rs_analyzer.py.

Punch list validation:
1. 30-equity fixture writes expected number of transition findings + 1 summary
2. Re-run idempotent (same data → same results)
3. Zero de_* SQL — only JIP client methods called
4. Zero float in any financial field passed to store_finding
5. V1 regression: classify_quadrant deterministic

All DB and embedding calls are mocked — no real DB or API calls.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.rs_analyzer import (
    AGENT_ID,
    AGENT_TYPE,
    Quadrant,
    classify_quadrant,
    run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

IST = timezone.utc  # Use UTC for tests; tz-awareness is what matters


def _make_data_as_of() -> datetime:
    return datetime(2026, 4, 13, 10, 0, 0, tzinfo=IST)


def _equity(
    symbol: str,
    rs_composite: str,
    rs_momentum: str,
    company_name: str | None = None,
    sector: str = "Technology",
) -> dict[str, Any]:
    """Build a fixture equity dict matching JIP equity universe shape."""
    return {
        "id": symbol,
        "symbol": symbol,
        "company_name": company_name or f"{symbol} Ltd",
        "sector": sector,
        "rs_composite": Decimal(rs_composite),
        "rs_momentum": Decimal(rs_momentum),
        "rs_1w": Decimal("0.5"),
        "rs_1m": Decimal("1.0"),
        "rs_3m": Decimal("2.0"),
        "rs_6m": Decimal("3.0"),
        "rs_12m": Decimal("4.0"),
        "rs_date": "2026-04-13",
        "tech_date": "2026-04-13",
    }


def _build_30_equity_fixture() -> list[dict[str, Any]]:
    """30-equity fixture with known quadrant distribution.

    Distribution:
    - 8 LEADING  (rs_composite > 0, rs_momentum > 0)
    - 7 IMPROVING(rs_composite < 0, rs_momentum > 0)
    - 6 WEAKENING(rs_composite > 0, rs_momentum < 0)
    - 9 LAGGING  (rs_composite < 0, rs_momentum < 0)

    On first run (no prior history):
    - Notable (LEADING + IMPROVING) = 8 + 7 = 15 findings written
    - Plus 1 summary finding = 16 total store_finding calls
    """
    equities = []

    # 8 LEADING
    for i in range(8):
        equities.append(
            _equity(
                f"LEAD{i:02d}",
                rs_composite=f"0.{i + 1}",
                rs_momentum=f"0.0{i + 1}",
                sector="Banking",
            )
        )

    # 7 IMPROVING
    for i in range(7):
        equities.append(
            _equity(
                f"IMPR{i:02d}",
                rs_composite=f"-0.{i + 1}",
                rs_momentum=f"0.0{i + 1}",
                sector="IT",
            )
        )

    # 6 WEAKENING
    for i in range(6):
        equities.append(
            _equity(
                f"WEAK{i:02d}",
                rs_composite=f"0.{i + 1}",
                rs_momentum=f"-0.0{i + 1}",
                sector="FMCG",
            )
        )

    # 9 LAGGING
    for i in range(9):
        equities.append(
            _equity(
                f"LAGG{i:02d}",
                rs_composite=f"-0.{i + 1}",
                rs_momentum=f"-0.0{i + 1}",
                sector="Pharma",
            )
        )

    return equities


# ---------------------------------------------------------------------------
# Unit: classify_quadrant
# ---------------------------------------------------------------------------


def test_classify_quadrant_leading() -> None:
    result = classify_quadrant(Decimal("0.5"), Decimal("0.1"))
    assert result == Quadrant.LEADING


def test_classify_quadrant_improving() -> None:
    result = classify_quadrant(Decimal("-0.5"), Decimal("0.1"))
    assert result == Quadrant.IMPROVING


def test_classify_quadrant_weakening() -> None:
    result = classify_quadrant(Decimal("0.5"), Decimal("-0.1"))
    assert result == Quadrant.WEAKENING


def test_classify_quadrant_lagging() -> None:
    result = classify_quadrant(Decimal("-0.5"), Decimal("-0.1"))
    assert result == Quadrant.LAGGING


def test_classify_quadrant_zero_composite_treated_as_negative() -> None:
    """Zero on rs_composite → treated as negative (spec uses strict >)."""
    result = classify_quadrant(Decimal("0"), Decimal("0.1"))
    assert result == Quadrant.IMPROVING


def test_classify_quadrant_zero_momentum_treated_as_negative() -> None:
    """Zero on rs_momentum → treated as negative (spec uses strict >)."""
    result = classify_quadrant(Decimal("0.5"), Decimal("0"))
    assert result == Quadrant.WEAKENING


def test_classify_quadrant_both_zero_lagging() -> None:
    """Both zero → LAGGING (both negative by strict > rule)."""
    result = classify_quadrant(Decimal("0"), Decimal("0"))
    assert result == Quadrant.LAGGING


def test_classify_quadrant_deterministic() -> None:
    """Same inputs always produce same output (V1 regression)."""
    for _ in range(5):
        assert classify_quadrant(Decimal("1.5"), Decimal("0.3")) == Quadrant.LEADING
        assert classify_quadrant(Decimal("-1.0"), Decimal("0.5")) == Quadrant.IMPROVING


# ---------------------------------------------------------------------------
# Integration-style: run() with mocked DB + JIP + store_finding
# ---------------------------------------------------------------------------


def _make_mock_store_finding() -> AsyncMock:
    """Return an AsyncMock for store_finding that returns a fake ORM object."""
    mock_row = MagicMock()
    mock_row.id = "fake-uuid"
    mock = AsyncMock(return_value=mock_row)
    return mock


def _make_mock_list_findings_no_history() -> AsyncMock:
    """Mock list_findings to return [] (first run — no prior findings)."""
    return AsyncMock(return_value=[])


@pytest.mark.asyncio
async def test_run_first_run_writes_expected_findings() -> None:
    """First run with 30-equity fixture: writes 15 notable + 1 summary = 16 calls."""
    equities = _build_30_equity_fixture()  # 8 LEADING + 7 IMPROVING + 6 WEAKENING + 9 LAGGING

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=equities)

    with (
        patch("backend.agents.rs_analyzer.store_finding", new_callable=AsyncMock) as mock_store,
        patch(
            "backend.agents.rs_analyzer.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_store.return_value = MagicMock(id="fake-uuid")

        result = await run(mock_db, mock_jip, _make_data_as_of())

    # 8 LEADING + 7 IMPROVING notable + 1 summary
    expected_notable = 8 + 7  # 15
    expected_summary = 1
    expected_total = expected_notable + expected_summary  # 16

    assert mock_store.call_count == expected_total, (
        f"Expected {expected_total} store_finding calls, got {mock_store.call_count}"
    )
    assert result["analyzed"] == 30
    assert result["findings_written"] == expected_total


@pytest.mark.asyncio
async def test_run_summary_finding_entity_is_market() -> None:
    """The final (summary) finding must have entity='market', entity_type='summary'."""
    equities = _build_30_equity_fixture()[:5]  # use fewer for speed

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=equities)

    with (
        patch("backend.agents.rs_analyzer.store_finding", new_callable=AsyncMock) as mock_store,
        patch(
            "backend.agents.rs_analyzer.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_store.return_value = MagicMock(id="fake-uuid")
        await run(mock_db, mock_jip, _make_data_as_of())

    # Last call should be the summary
    last_call_kwargs = mock_store.call_args_list[-1].kwargs
    assert last_call_kwargs["entity"] == "market"
    assert last_call_kwargs["entity_type"] == "summary"
    assert last_call_kwargs["finding_type"] == "analysis_summary"
    assert last_call_kwargs["agent_id"] == AGENT_ID
    assert last_call_kwargs["agent_type"] == AGENT_TYPE


@pytest.mark.asyncio
async def test_run_no_float_in_financial_fields() -> None:
    """Assert zero float in any financial field passed to store_finding.

    Checks: confidence and rs_composite/rs_momentum in evidence are Decimal or str.
    """
    equities = _build_30_equity_fixture()

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=equities)

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with (
        patch("backend.agents.rs_analyzer.store_finding", side_effect=capture_store),
        patch(
            "backend.agents.rs_analyzer.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        await run(mock_db, mock_jip, _make_data_as_of())

    for call_kwargs in stored_calls:
        confidence = call_kwargs.get("confidence")
        assert not isinstance(confidence, float), (
            f"confidence must not be float, got {type(confidence).__name__}: {confidence}"
        )
        assert isinstance(confidence, Decimal), (
            f"confidence must be Decimal, got {type(confidence).__name__}"
        )

        evidence = call_kwargs.get("evidence") or {}
        for key in ("rs_composite", "rs_momentum", "coverage_pct"):
            if key in evidence:
                val = evidence[key]
                assert not isinstance(val, float), (
                    f"evidence['{key}'] must not be float, got {type(val).__name__}: {val}"
                )


@pytest.mark.asyncio
async def test_run_transition_detection_writes_transition_findings() -> None:
    """When prior quadrant differs, transitions are detected and written."""
    # 2 equities that previously were LAGGING but now are LEADING
    equities = [
        _equity("TRNS00", rs_composite="0.5", rs_momentum="0.3"),  # now LEADING
        _equity("TRNS01", rs_composite="0.8", rs_momentum="0.4"),  # now LEADING
        _equity("STAY00", rs_composite="-0.5", rs_momentum="-0.3"),  # still LAGGING
    ]

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=equities)

    def _make_prior_finding(quadrant: Quadrant) -> MagicMock:
        finding = MagicMock()
        finding.evidence = {"quadrant": quadrant.value}
        return finding

    async def mock_list_findings(db: Any, entity: str, **kwargs: Any) -> list[MagicMock]:
        if entity in ("TRNS00", "TRNS01"):
            return [_make_prior_finding(Quadrant.LAGGING)]  # prior was LAGGING
        elif entity == "STAY00":
            return [_make_prior_finding(Quadrant.LAGGING)]  # prior was LAGGING, still LAGGING
        return []

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with (
        patch("backend.agents.rs_analyzer.store_finding", side_effect=capture_store),
        patch("backend.agents.rs_analyzer.list_findings", side_effect=mock_list_findings),
    ):
        result = await run(mock_db, mock_jip, _make_data_as_of())

    # 2 transitions + 1 update for STAY00 (same quadrant path) + 1 summary = 4
    transition_calls = [c for c in stored_calls if c.get("finding_type") == "quadrant_transition"]
    assert len(transition_calls) == 2, f"Expected 2 transitions, got {len(transition_calls)}"
    assert result["transitions"] == 2


@pytest.mark.asyncio
async def test_run_idempotent_same_data_as_of() -> None:
    """Re-run with same data produces same finding count (store_finding handles upsert)."""
    equities = _build_30_equity_fixture()

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=equities)

    data_as_of = _make_data_as_of()

    call_counts: list[int] = []

    for _ in range(2):
        with (
            patch("backend.agents.rs_analyzer.store_finding", new_callable=AsyncMock) as mock_store,
            patch(
                "backend.agents.rs_analyzer.list_findings",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_store.return_value = MagicMock(id="fake-uuid")
            await run(mock_db, mock_jip, data_as_of)
            call_counts.append(mock_store.call_count)

    assert call_counts[0] == call_counts[1], (
        f"Idempotent check failed: run 1={call_counts[0]}, run 2={call_counts[1]}"
    )


@pytest.mark.asyncio
async def test_run_zero_de_star_sql() -> None:
    """Agent must never reference de_* tables directly — only JIP client methods."""
    import inspect

    import backend.agents.rs_analyzer as module

    source = inspect.getsource(module)

    # Ensure no direct de_* table references (the JIP client handles those)
    de_table_pattern = re.compile(r"\bde_[a-z_]+\b")
    matches = de_table_pattern.findall(source)
    assert matches == [], (
        f"rs_analyzer.py contains direct de_* table references: {matches}. "
        "Use JIPDataService methods only."
    )

    # Ensure no raw SQL text() calls in the agent module itself
    assert "text(" not in source or "from sqlalchemy" not in source, (
        "rs_analyzer.py should not use raw SQL text() — use JIPDataService and store_finding"
    )


@pytest.mark.asyncio
async def test_run_skips_equities_with_missing_rs() -> None:
    """Equities with None rs_composite or rs_momentum are skipped gracefully."""
    equities = [
        _equity("GOOD00", rs_composite="0.5", rs_momentum="0.3"),  # valid
        {
            "symbol": "MISS00",
            "company_name": "Missing Co",
            "sector": "IT",
            "rs_composite": None,  # missing
            "rs_momentum": Decimal("0.1"),
        },
        {
            "symbol": "MISS01",
            "company_name": "Missing Co 2",
            "sector": "IT",
            "rs_composite": Decimal("0.5"),
            "rs_momentum": None,  # missing
        },
    ]

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=equities)

    with (
        patch("backend.agents.rs_analyzer.store_finding", new_callable=AsyncMock) as mock_store,
        patch(
            "backend.agents.rs_analyzer.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_store.return_value = MagicMock(id="fake-uuid")
        result = await run(mock_db, mock_jip, _make_data_as_of())

    # Only GOOD00 analyzed + 1 summary
    assert result["analyzed"] == 1
    # GOOD00 is LEADING → notable → 1 finding + 1 summary = 2
    assert mock_store.call_count == 2


@pytest.mark.asyncio
async def test_run_empty_equity_universe() -> None:
    """Empty universe: only summary finding written, analyzed=0."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=[])

    with (
        patch("backend.agents.rs_analyzer.store_finding", new_callable=AsyncMock) as mock_store,
        patch(
            "backend.agents.rs_analyzer.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_store.return_value = MagicMock(id="fake-uuid")
        result = await run(mock_db, mock_jip, _make_data_as_of())

    assert result["analyzed"] == 0
    assert result["transitions"] == 0
    assert result["findings_written"] == 1  # only summary
    assert mock_store.call_count == 1


@pytest.mark.asyncio
async def test_run_naive_datetime_raises() -> None:
    """Naive datetime (no tzinfo) should raise ValueError."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()

    with pytest.raises(ValueError, match="timezone-aware"):
        await run(mock_db, mock_jip, datetime(2026, 4, 13, 10, 0, 0))  # naive


@pytest.mark.asyncio
async def test_run_only_calls_jip_client_methods() -> None:
    """Verify agent only calls get_equity_universe on JIPDataService (no direct SQL)."""
    equities = _build_30_equity_fixture()[:3]

    mock_db = AsyncMock()
    mock_jip = MagicMock()  # Use MagicMock to detect unexpected calls
    mock_jip.get_equity_universe = AsyncMock(return_value=equities)

    with (
        patch("backend.agents.rs_analyzer.store_finding", new_callable=AsyncMock) as mock_store,
        patch(
            "backend.agents.rs_analyzer.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_store.return_value = MagicMock(id="fake-uuid")
        await run(mock_db, mock_jip, _make_data_as_of())

    # Only get_equity_universe should have been called on the JIP client
    mock_jip.get_equity_universe.assert_called_once_with(benchmark="NIFTY 500")


@pytest.mark.asyncio
async def test_run_transition_evidence_has_prior_quadrant() -> None:
    """Transition findings must include prior_quadrant in evidence."""
    equities = [
        _equity("TRNS00", rs_composite="0.5", rs_momentum="0.3"),  # now LEADING
    ]

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=equities)

    def _make_prior(quadrant: Quadrant) -> MagicMock:
        f = MagicMock()
        f.evidence = {"quadrant": quadrant.value}
        return f

    async def mock_list_findings(db: Any, entity: str, **kwargs: Any) -> list:
        return [_make_prior(Quadrant.LAGGING)]

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with (
        patch("backend.agents.rs_analyzer.store_finding", side_effect=capture_store),
        patch("backend.agents.rs_analyzer.list_findings", side_effect=mock_list_findings),
    ):
        await run(mock_db, mock_jip, _make_data_as_of())

    transition = next(c for c in stored_calls if c.get("finding_type") == "quadrant_transition")
    assert transition["evidence"]["prior_quadrant"] == Quadrant.LAGGING.value
    assert transition["evidence"]["quadrant"] == Quadrant.LEADING.value
    assert transition["evidence"]["rs_crossed_zero"] is True  # crossed from negative to positive
