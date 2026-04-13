"""Unit tests for backend/agents/decisions_generator.py.

Punch list validation:
1. 12-finding fixture (8 equity + 4 sector) writes exactly 12 decisions
2. Re-run is a clean no-op (0 new decisions written)
3. Zero float in any decision's supporting_data or confidence
4. Correct decision_type mapping per spec §23.2
5. supporting_data references source finding_id
6. Naive datetime raises ValueError
7. Empty findings → 0 decisions, clean summary
8. confidence is Decimal, not float
9. horizon_end_date = data_as_of + 20 days
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.decisions_generator import (
    AGENT_ID,
    HORIZON_DAYS,
    HORIZON_LABEL,
    _map_breadth_divergence,
    _map_equity_quadrant,
    _map_equity_transition,
    _map_sector_rotation,
    run,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IST = timezone.utc  # UTC used in tests; tz-awareness is what matters


def _make_data_as_of() -> datetime:
    return datetime(2026, 4, 13, 10, 0, 0, tzinfo=IST)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_finding(
    agent_id: str,
    finding_type: str,
    entity: str,
    entity_type: str = "equity",
    evidence: dict[str, Any] | None = None,
    confidence: Decimal = Decimal("0.80"),
    title: str = "Test finding",
) -> MagicMock:
    """Build a mock AtlasIntelligence object."""
    finding = MagicMock()
    finding.id = uuid.uuid4()
    finding.agent_id = agent_id
    finding.finding_type = finding_type
    finding.entity = entity
    finding.entity_type = entity_type
    finding.evidence = evidence or {}
    finding.confidence = confidence
    finding.title = title
    return finding


def _build_12_finding_fixture() -> list[MagicMock]:
    """12-finding fixture: 8 equity + 4 sector.

    Equity (8 findings from rs-analyzer):
      quadrant_classification:
        - RELIANCE → LEADING   → buy_signal
        - TCS      → IMPROVING → buy_signal
        - INFY     → WEAKENING → sell_signal
        - WIPRO    → LAGGING   → sell_signal

      quadrant_transition:
        - HDFC  → to LEADING   → buy_signal
        - ITC   → to IMPROVING → buy_signal
        - BAJAJ → to WEAKENING → sell_signal
        - MARUT → to LAGGING   → sell_signal

    Sector (4 findings from sector-analyst):
      sector_rotation:
        - IT sector   → LEADING   → overweight
        - FMCG sector → WEAKENING → avoid

      breadth_divergence:
        - Banks sector → bullish_rs_weak_breadth  → avoid
        - Auto sector  → bearish_rs_strong_breadth → overweight
    """
    return [
        # Equity quadrant_classification (4)
        _make_finding(
            "rs-analyzer",
            "quadrant_classification",
            "RELIANCE",
            evidence={"quadrant": "LEADING", "rs_composite": "0.5", "rs_momentum": "0.3"},
        ),
        _make_finding(
            "rs-analyzer",
            "quadrant_classification",
            "TCS",
            evidence={"quadrant": "IMPROVING", "rs_composite": "-0.2", "rs_momentum": "0.1"},
        ),
        _make_finding(
            "rs-analyzer",
            "quadrant_classification",
            "INFY",
            evidence={"quadrant": "WEAKENING", "rs_composite": "0.1", "rs_momentum": "-0.2"},
        ),
        _make_finding(
            "rs-analyzer",
            "quadrant_classification",
            "WIPRO",
            evidence={"quadrant": "LAGGING", "rs_composite": "-0.3", "rs_momentum": "-0.1"},
        ),
        # Equity quadrant_transition (4)
        _make_finding(
            "rs-analyzer",
            "quadrant_transition",
            "HDFC",
            evidence={"quadrant": "LEADING", "prior_quadrant": "IMPROVING"},
        ),
        _make_finding(
            "rs-analyzer",
            "quadrant_transition",
            "ITC",
            evidence={"quadrant": "IMPROVING", "prior_quadrant": "LAGGING"},
        ),
        _make_finding(
            "rs-analyzer",
            "quadrant_transition",
            "BAJAJ",
            evidence={"quadrant": "WEAKENING", "prior_quadrant": "LEADING"},
        ),
        _make_finding(
            "rs-analyzer",
            "quadrant_transition",
            "MARUT",
            evidence={"quadrant": "LAGGING", "prior_quadrant": "WEAKENING"},
        ),
        # Sector sector_rotation (2)
        _make_finding(
            "sector-analyst",
            "sector_rotation",
            "IT",
            entity_type="sector",
            evidence={"quadrant": "LEADING", "prior_quadrant": "IMPROVING"},
        ),
        _make_finding(
            "sector-analyst",
            "sector_rotation",
            "FMCG",
            entity_type="sector",
            evidence={"quadrant": "WEAKENING", "prior_quadrant": "LEADING"},
        ),
        # Sector breadth_divergence (2)
        _make_finding(
            "sector-analyst",
            "breadth_divergence",
            "BANKS",
            entity_type="sector",
            evidence={
                "divergence_type": "bullish_rs_weak_breadth",
                "avg_rs_composite": "0.3",
                "pct_above_200dma": "35",
            },
        ),
        _make_finding(
            "sector-analyst",
            "breadth_divergence",
            "AUTO",
            entity_type="sector",
            evidence={
                "divergence_type": "bearish_rs_strong_breadth",
                "avg_rs_composite": "-0.2",
                "pct_above_200dma": "72",
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_db(decision_exists: bool = False) -> AsyncMock:
    """Build an async mock DB session where _decision_exists returns decision_exists.

    db.execute() is an AsyncMock so `await db.execute(...)` returns a MagicMock.
    We configure scalar_one_or_none() on that MagicMock directly.
    """
    mock_db = AsyncMock()
    # AsyncMock: awaiting mock_db.execute() returns mock_db.execute.return_value
    # We need scalar_one_or_none to be a regular (not async) callable returning a value.
    execute_result = MagicMock()
    if decision_exists:
        execute_result.scalar_one_or_none.return_value = uuid.uuid4()
    else:
        execute_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=execute_result)
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    return mock_db


def _patch_list_findings(findings: list[MagicMock]) -> dict[tuple[str, str], list[MagicMock]]:
    """Return a dispatch dict mapping (agent_id, finding_type) → findings list."""
    by_key: dict[tuple[str, str], list[MagicMock]] = {
        ("rs-analyzer", "quadrant_classification"): [],
        ("rs-analyzer", "quadrant_transition"): [],
        ("sector-analyst", "sector_rotation"): [],
        ("sector-analyst", "breadth_divergence"): [],
    }
    for f in findings:
        key = (f.agent_id, f.finding_type)
        if key in by_key:
            by_key[key].append(f)
    return by_key


async def _mock_list_findings_factory(
    dispatch: dict[tuple[str, str], list[MagicMock]],
) -> Any:
    """Return an async side_effect callable for list_findings."""

    async def _side_effect(
        db: Any,
        agent_id: str | None = None,
        finding_type: str | None = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> list[MagicMock]:
        return dispatch.get((agent_id, finding_type), [])

    return _side_effect


# ---------------------------------------------------------------------------
# Punch list test 1: 12-finding fixture → exactly 12 decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_12_finding_fixture_writes_12_decisions() -> None:
    """Main punch list: 12 findings → exactly 12 decisions written."""
    findings = _build_12_finding_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []

    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        result = await run(mock_db, _make_data_as_of())

    assert result["findings_read"] == 12, (
        f"Expected 12 findings read, got {result['findings_read']}"
    )
    assert result["decisions_written"] == 12, (
        f"Expected 12 decisions written, got {result['decisions_written']}"
    )
    assert result["decisions_skipped"] == 0, (
        f"Expected 0 skipped, got {result['decisions_skipped']}"
    )
    assert len(added_decisions) == 12, f"Expected 12 db.add calls, got {len(added_decisions)}"


# ---------------------------------------------------------------------------
# Punch list test 2: Re-run is a clean no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerun_is_noop() -> None:
    """Re-run with same data_as_of writes 0 new decisions (idempotent)."""
    findings = _build_12_finding_fixture()
    dispatch = _patch_list_findings(findings)

    # All decisions already exist → _decision_exists returns non-None
    mock_db = _make_mock_db(decision_exists=True)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        result = await run(mock_db, _make_data_as_of())

    assert result["decisions_written"] == 0, (
        f"Re-run should write 0 decisions, got {result['decisions_written']}"
    )
    # All 12 should be skipped
    assert result["decisions_skipped"] == 12, (
        f"Re-run should skip 12 decisions, got {result['decisions_skipped']}"
    )
    # db.add should never be called
    mock_db.add.assert_not_called()
    # db.commit should not be called when nothing is written
    mock_db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Punch list test 3: Zero float in supporting_data and confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_float_in_decisions() -> None:
    """No float values in any decision's supporting_data or confidence."""
    findings = _build_12_finding_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []

    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    for decision in added_decisions:
        assert not isinstance(decision.confidence, float), (
            f"confidence must not be float: {type(decision.confidence).__name__}"
        )
        assert isinstance(decision.confidence, Decimal), (
            f"confidence must be Decimal: {type(decision.confidence).__name__}"
        )
        # Check supporting_data recursively for floats
        _assert_no_float_in_dict(decision.supporting_data, f"decision for {decision.entity}")


def _assert_no_float_in_dict(data: Any, context: str) -> None:
    """Recursively assert no float values in a dict or nested structure."""
    if isinstance(data, dict):
        for key, value in data.items():
            assert not isinstance(value, float), (
                f"{context}: supporting_data['{key}'] is float: {value!r}"
            )
            _assert_no_float_in_dict(value, f"{context}['{key}']")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            assert not isinstance(item, float), f"{context}[{i}] is float: {item!r}"
            _assert_no_float_in_dict(item, f"{context}[{i}]")


# ---------------------------------------------------------------------------
# Punch list test 4: Correct decision_type mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_correct_decision_type_mapping() -> None:
    """Each finding maps to the correct decision_type per spec §23.2."""
    findings = _build_12_finding_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []

    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    decisions_by_entity = {d.entity: d for d in added_decisions}

    # Equity quadrant_classification
    assert decisions_by_entity["RELIANCE"].decision_type == "buy_signal"
    assert decisions_by_entity["TCS"].decision_type == "buy_signal"
    assert decisions_by_entity["INFY"].decision_type == "sell_signal"
    assert decisions_by_entity["WIPRO"].decision_type == "sell_signal"

    # Equity quadrant_transition
    assert decisions_by_entity["HDFC"].decision_type == "buy_signal"
    assert decisions_by_entity["ITC"].decision_type == "buy_signal"
    assert decisions_by_entity["BAJAJ"].decision_type == "sell_signal"
    assert decisions_by_entity["MARUT"].decision_type == "sell_signal"

    # Sector rotation
    assert decisions_by_entity["IT"].decision_type == "overweight"
    assert decisions_by_entity["FMCG"].decision_type == "avoid"

    # Breadth divergence
    assert decisions_by_entity["BANKS"].decision_type == "avoid"  # bullish_rs_weak_breadth
    assert decisions_by_entity["AUTO"].decision_type == "overweight"  # bearish_rs_strong_breadth


# ---------------------------------------------------------------------------
# Punch list test 5: supporting_data references finding_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supporting_data_references_finding_id() -> None:
    """Each decision's supporting_data contains the source finding_id."""
    findings = _build_12_finding_fixture()
    dispatch = _patch_list_findings(findings)
    finding_ids = {str(f.id) for f in findings}

    added_decisions: list[Any] = []

    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    for decision in added_decisions:
        assert "finding_id" in decision.supporting_data, (
            f"Decision for {decision.entity} missing finding_id in supporting_data"
        )
        fid = decision.supporting_data["finding_id"]
        assert fid in finding_ids, f"finding_id {fid!r} not in known finding IDs"


# ---------------------------------------------------------------------------
# Punch list test 6: Naive datetime raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_naive_datetime_raises() -> None:
    """Naive datetime (no tzinfo) should raise ValueError."""
    mock_db = AsyncMock()
    with pytest.raises(ValueError, match="timezone-aware"):
        await run(mock_db, datetime(2026, 4, 13, 10, 0, 0))  # naive


# ---------------------------------------------------------------------------
# Punch list test 7: Empty findings → 0 decisions + clean summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_findings_no_decisions() -> None:
    """No findings → 0 decisions written, summary is clean."""
    mock_db = _make_mock_db(decision_exists=False)

    async def empty_list_findings(**kwargs: Any) -> list:
        return []

    with patch("backend.agents.decisions_generator.list_findings", side_effect=empty_list_findings):
        result = await run(mock_db, _make_data_as_of())

    assert result["findings_read"] == 0
    assert result["decisions_written"] == 0
    assert result["decisions_skipped"] == 0
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Punch list test 8: confidence is Decimal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confidence_is_decimal() -> None:
    """All decision confidence values must be Decimal instances."""
    findings = _build_12_finding_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []

    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    for decision in added_decisions:
        assert isinstance(decision.confidence, Decimal), (
            f"Decision for {decision.entity}: confidence type is "
            f"{type(decision.confidence).__name__}, expected Decimal"
        )


# ---------------------------------------------------------------------------
# Punch list test 9: horizon_end_date = data_as_of + 20 days
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_horizon_end_date_correct() -> None:
    """All 20-day decisions have horizon_end_date = data_as_of.date() + 20 days."""
    from datetime import timedelta

    findings = _build_12_finding_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []

    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)
    data_as_of = _make_data_as_of()
    expected_horizon_end = data_as_of.date() + timedelta(days=HORIZON_DAYS)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, data_as_of)

    for decision in added_decisions:
        assert decision.horizon == HORIZON_LABEL, (
            f"Decision for {decision.entity}: horizon is {decision.horizon!r}, "
            f"expected {HORIZON_LABEL!r}"
        )
        assert decision.horizon_end_date == expected_horizon_end, (
            f"Decision for {decision.entity}: horizon_end_date is "
            f"{decision.horizon_end_date}, expected {expected_horizon_end}"
        )


# ---------------------------------------------------------------------------
# Unit: mapping functions
# ---------------------------------------------------------------------------


def test_map_equity_quadrant_leading() -> None:
    finding = _make_finding(
        "rs-analyzer", "quadrant_classification", "X", evidence={"quadrant": "LEADING"}
    )
    result = _map_equity_quadrant(finding)
    assert result is not None
    assert result[0] == "buy_signal"
    assert result[1] == Decimal("0.85")


def test_map_equity_quadrant_improving() -> None:
    finding = _make_finding(
        "rs-analyzer", "quadrant_classification", "X", evidence={"quadrant": "IMPROVING"}
    )
    result = _map_equity_quadrant(finding)
    assert result is not None
    assert result[0] == "buy_signal"
    assert result[1] == Decimal("0.70")


def test_map_equity_quadrant_weakening() -> None:
    finding = _make_finding(
        "rs-analyzer", "quadrant_classification", "X", evidence={"quadrant": "WEAKENING"}
    )
    result = _map_equity_quadrant(finding)
    assert result is not None
    assert result[0] == "sell_signal"


def test_map_equity_quadrant_lagging() -> None:
    finding = _make_finding(
        "rs-analyzer", "quadrant_classification", "X", evidence={"quadrant": "LAGGING"}
    )
    result = _map_equity_quadrant(finding)
    assert result is not None
    assert result[0] == "sell_signal"


def test_map_equity_quadrant_unknown_returns_none() -> None:
    finding = _make_finding(
        "rs-analyzer", "quadrant_classification", "X", evidence={"quadrant": "UNKNOWN"}
    )
    result = _map_equity_quadrant(finding)
    assert result is None


def test_map_equity_transition_to_leading() -> None:
    finding = _make_finding(
        "rs-analyzer",
        "quadrant_transition",
        "X",
        evidence={"quadrant": "LEADING", "prior_quadrant": "IMPROVING"},
    )
    result = _map_equity_transition(finding)
    assert result is not None
    assert result[0] == "buy_signal"
    assert result[1] == Decimal("0.85")


def test_map_equity_transition_to_weakening() -> None:
    finding = _make_finding(
        "rs-analyzer",
        "quadrant_transition",
        "X",
        evidence={"quadrant": "WEAKENING", "prior_quadrant": "LEADING"},
    )
    result = _map_equity_transition(finding)
    assert result is not None
    assert result[0] == "sell_signal"


def test_map_sector_rotation_to_leading() -> None:
    finding = _make_finding(
        "sector-analyst",
        "sector_rotation",
        "IT",
        entity_type="sector",
        evidence={"quadrant": "LEADING", "prior_quadrant": "IMPROVING"},
    )
    result = _map_sector_rotation(finding)
    assert result is not None
    assert result[0] == "overweight"
    assert result[1] == Decimal("0.85")


def test_map_sector_rotation_to_weakening() -> None:
    finding = _make_finding(
        "sector-analyst",
        "sector_rotation",
        "FMCG",
        entity_type="sector",
        evidence={"quadrant": "WEAKENING", "prior_quadrant": "LEADING"},
    )
    result = _map_sector_rotation(finding)
    assert result is not None
    assert result[0] == "avoid"


def test_map_breadth_divergence_bullish_rs_weak_breadth() -> None:
    finding = _make_finding(
        "sector-analyst",
        "breadth_divergence",
        "BANKS",
        entity_type="sector",
        evidence={"divergence_type": "bullish_rs_weak_breadth"},
    )
    result = _map_breadth_divergence(finding)
    assert result is not None
    assert result[0] == "avoid"


def test_map_breadth_divergence_bearish_rs_strong_breadth() -> None:
    finding = _make_finding(
        "sector-analyst",
        "breadth_divergence",
        "AUTO",
        entity_type="sector",
        evidence={"divergence_type": "bearish_rs_strong_breadth"},
    )
    result = _map_breadth_divergence(finding)
    assert result is not None
    assert result[0] == "overweight"


def test_map_breadth_divergence_unknown_returns_none() -> None:
    finding = _make_finding(
        "sector-analyst",
        "breadth_divergence",
        "X",
        entity_type="sector",
        evidence={"divergence_type": "unknown_type"},
    )
    result = _map_breadth_divergence(finding)
    assert result is None


# ---------------------------------------------------------------------------
# Source agent integrity: no de_* SQL
# ---------------------------------------------------------------------------


def test_no_de_star_sql_in_decisions_generator() -> None:
    """Agent must never reference de_* tables directly."""
    import inspect
    import re

    import backend.agents.decisions_generator as module

    source = inspect.getsource(module)
    de_table_pattern = re.compile(r"\bde_[a-z_]+\b")
    matches = de_table_pattern.findall(source)
    assert matches == [], f"decisions_generator.py contains direct de_* table references: {matches}"


# ---------------------------------------------------------------------------
# Test: finding with no entity is skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finding_with_no_entity_skipped() -> None:
    """Findings with empty/None entity are skipped without error."""
    finding = _make_finding(
        "rs-analyzer",
        "quadrant_classification",
        "",
        evidence={"quadrant": "LEADING"},
    )
    finding.entity = None  # simulate missing entity

    dispatch = {
        ("rs-analyzer", "quadrant_classification"): [finding],
        ("rs-analyzer", "quadrant_transition"): [],
        ("sector-analyst", "sector_rotation"): [],
        ("sector-analyst", "breadth_divergence"): [],
    }

    mock_db = _make_mock_db(decision_exists=False)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        result = await run(mock_db, _make_data_as_of())

    assert result["decisions_written"] == 0
    mock_db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Test: source_agent is set to AGENT_ID on all decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_agent_is_decisions_generator() -> None:
    """All written decisions have source_agent == AGENT_ID."""
    findings = _build_12_finding_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []

    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    for decision in added_decisions:
        assert decision.source_agent == AGENT_ID, (
            f"Decision for {decision.entity}: source_agent is {decision.source_agent!r}, "
            f"expected {AGENT_ID!r}"
        )


# ---------------------------------------------------------------------------
# Test: status is always "active"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_decisions_status_active() -> None:
    """All written decisions start with status='active'."""
    findings = _build_12_finding_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []

    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    for decision in added_decisions:
        assert decision.status == "active", (
            f"Decision for {decision.entity}: status is {decision.status!r}, expected 'active'"
        )
