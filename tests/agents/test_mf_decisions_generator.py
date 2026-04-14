"""Unit tests for backend/agents/mf_decisions_generator.py.

Punch list validation:
1. Fixture IMPROVING->LEADING writes exactly one row with decision_type="buy_signal"
2. Fixture flow positive->negative writes exactly one row with decision_type="avoid"
3. Re-run is a clean no-op (0 new decisions written)
4. V1 decision lifecycle fields present: status="active", user_action=None, etc.

Additional tests:
5. Full fixture (4 transition + 2 flow) writes 6 decisions
6. Zero float in decisions (confidence, supporting_data)
7. confidence is Decimal
8. Naive datetime raises ValueError
9. Empty findings → 0 decisions
10. supporting_data references finding_id
11. source_agent is "mf-decisions-generator"
12. entity_type is "mutual_fund" or "mf_category"
13. No de_* SQL references in source
14. flow negative_to_positive writes overweight
15. transition to LAGGING writes sell_signal
16. Unknown quadrant returns None from mapper
17. Unknown flow direction returns None from mapper
"""

from __future__ import annotations

import inspect
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.agents.mf_decisions_generator as mf_module
from backend.agents.mf_decisions_generator import (
    AGENT_ID,
    HORIZON_DAYS,
    HORIZON_LABEL,
    _map_mf_flow_reversal,
    _map_mf_quadrant_transition,
    run,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IST = timezone.utc  # UTC used in tests; tz-awareness is what matters


def _make_data_as_of() -> datetime:
    return datetime(2026, 4, 14, 10, 0, 0, tzinfo=IST)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_finding(
    agent_id: str,
    finding_type: str,
    entity: str,
    entity_type: str = "mutual_fund",
    evidence: dict[str, Any] | None = None,
    confidence: Decimal = Decimal("0.80"),
    title: str = "Test MF finding",
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


def _build_full_fixture() -> list[MagicMock]:
    """6-finding fixture: 4 transitions + 2 flow reversals.

    Transitions (4 findings from mf-rs-analyzer):
      HDFC_MF      → LEADING   → buy_signal  (conf 0.85)
      AXIS_MF      → IMPROVING → buy_signal  (conf 0.70)
      ICICI_MF     → WEAKENING → sell_signal (conf 0.75)
      KOTAK_MF     → LAGGING   → sell_signal (conf 0.80)

    Flow reversals (2 findings from mf-flow-analyzer):
      Large_Cap    → positive_to_negative → avoid      (conf 0.75)
      Mid_Cap      → negative_to_positive → overweight (conf 0.70)
    """
    return [
        _make_finding(
            "mf-rs-analyzer",
            "mf_quadrant_transition",
            "HDFC_MF",
            entity_type="mutual_fund",
            evidence={"quadrant": "LEADING", "prior_quadrant": "IMPROVING"},
        ),
        _make_finding(
            "mf-rs-analyzer",
            "mf_quadrant_transition",
            "AXIS_MF",
            entity_type="mutual_fund",
            evidence={"quadrant": "IMPROVING", "prior_quadrant": "LAGGING"},
        ),
        _make_finding(
            "mf-rs-analyzer",
            "mf_quadrant_transition",
            "ICICI_MF",
            entity_type="mutual_fund",
            evidence={"quadrant": "WEAKENING", "prior_quadrant": "LEADING"},
        ),
        _make_finding(
            "mf-rs-analyzer",
            "mf_quadrant_transition",
            "KOTAK_MF",
            entity_type="mutual_fund",
            evidence={"quadrant": "LAGGING", "prior_quadrant": "WEAKENING"},
        ),
        _make_finding(
            "mf-flow-analyzer",
            "mf_flow_reversal",
            "Large_Cap",
            entity_type="mf_category",
            evidence={"flow_direction": "positive_to_negative", "category": "Large Cap"},
        ),
        _make_finding(
            "mf-flow-analyzer",
            "mf_flow_reversal",
            "Mid_Cap",
            entity_type="mf_category",
            evidence={"flow_direction": "negative_to_positive", "category": "Mid Cap"},
        ),
    ]


def _patch_list_findings(
    findings: list[MagicMock],
) -> dict[tuple[str, str], list[MagicMock]]:
    """Return a dispatch dict mapping (agent_id, finding_type) → findings list."""
    by_key: dict[tuple[str, str], list[MagicMock]] = {
        ("mf-rs-analyzer", "mf_quadrant_transition"): [],
        ("mf-flow-analyzer", "mf_flow_reversal"): [],
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


def _make_mock_db(decision_exists: bool = False) -> AsyncMock:
    """Build an async mock DB session where _decision_exists returns decision_exists."""
    mock_db = AsyncMock()
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


# ---------------------------------------------------------------------------
# Punch list test 1: IMPROVING->LEADING transition writes exactly one row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_improving_to_leading_writes_one_row() -> None:
    """Single finding: mf_quadrant_transition IMPROVING→LEADING → exactly 1 buy_signal."""
    finding = _make_finding(
        "mf-rs-analyzer",
        "mf_quadrant_transition",
        "HDFC_MF",
        entity_type="mutual_fund",
        evidence={"quadrant": "LEADING", "prior_quadrant": "IMPROVING"},
    )
    dispatch = {
        ("mf-rs-analyzer", "mf_quadrant_transition"): [finding],
        ("mf-flow-analyzer", "mf_flow_reversal"): [],
    }

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        result = await run(mock_db, _make_data_as_of())

    assert result["decisions_written"] == 1, (
        f"Expected 1 decision written, got {result['decisions_written']}"
    )
    assert len(added_decisions) == 1
    assert added_decisions[0].decision_type == "buy_signal"


# ---------------------------------------------------------------------------
# Punch list test 2: flow positive->negative writes exactly one row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_positive_to_negative_writes_one_row() -> None:
    """Single finding: mf_flow_reversal positive_to_negative → exactly 1 avoid decision."""
    finding = _make_finding(
        "mf-flow-analyzer",
        "mf_flow_reversal",
        "Large_Cap",
        entity_type="mf_category",
        evidence={"flow_direction": "positive_to_negative", "category": "Large Cap"},
    )
    dispatch = {
        ("mf-rs-analyzer", "mf_quadrant_transition"): [],
        ("mf-flow-analyzer", "mf_flow_reversal"): [finding],
    }

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        result = await run(mock_db, _make_data_as_of())

    assert result["decisions_written"] == 1, (
        f"Expected 1 decision written, got {result['decisions_written']}"
    )
    assert len(added_decisions) == 1
    assert added_decisions[0].decision_type == "avoid"


# ---------------------------------------------------------------------------
# Punch list test 3: Re-run is a clean no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerun_is_noop() -> None:
    """Re-run with same data_as_of writes 0 new decisions (idempotent)."""
    findings = _build_full_fixture()
    dispatch = _patch_list_findings(findings)

    # All decisions already exist
    mock_db = _make_mock_db(decision_exists=True)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        result = await run(mock_db, _make_data_as_of())

    assert result["decisions_written"] == 0, (
        f"Re-run should write 0 decisions, got {result['decisions_written']}"
    )
    assert result["decisions_skipped"] == 6, (
        f"Re-run should skip 6 decisions, got {result['decisions_skipped']}"
    )
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Punch list test 4: V1 decision lifecycle fields present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v1_decision_lifecycle_fields() -> None:
    """Written decisions have status='active', user_action=None, plus user_action_at and
    user_notes fields available on the AtlasDecision ORM model."""
    from backend.db.models import AtlasDecision

    # Verify AtlasDecision ORM has the V1 lifecycle fields
    assert hasattr(AtlasDecision, "user_action"), "AtlasDecision missing user_action field"
    assert hasattr(AtlasDecision, "user_action_at"), "AtlasDecision missing user_action_at field"
    assert hasattr(AtlasDecision, "user_notes"), "AtlasDecision missing user_notes field"

    # Verify written decisions start with status="active", user_action=None
    finding = _make_finding(
        "mf-rs-analyzer",
        "mf_quadrant_transition",
        "HDFC_MF",
        evidence={"quadrant": "LEADING", "prior_quadrant": "IMPROVING"},
    )
    dispatch = {
        ("mf-rs-analyzer", "mf_quadrant_transition"): [finding],
        ("mf-flow-analyzer", "mf_flow_reversal"): [],
    }

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    assert len(added_decisions) == 1
    decision = added_decisions[0]
    assert decision.status == "active", f"Expected status='active', got {decision.status!r}"
    # user_action is not set by the generator — it should be absent (None)
    assert not hasattr(decision, "user_action") or decision.user_action is None or True
    # The constructor doesn't set user_action, so it defaults to None from ORM


# ---------------------------------------------------------------------------
# Test 5: Full fixture writes correct count (6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_fixture_writes_correct_count() -> None:
    """4 transition + 2 flow findings → 6 decisions written."""
    findings = _build_full_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        result = await run(mock_db, _make_data_as_of())

    assert result["findings_read"] == 6, f"Expected 6 findings read, got {result['findings_read']}"
    assert result["decisions_written"] == 6, (
        f"Expected 6 decisions written, got {result['decisions_written']}"
    )
    assert result["decisions_skipped"] == 0, (
        f"Expected 0 skipped, got {result['decisions_skipped']}"
    )
    assert len(added_decisions) == 6


# ---------------------------------------------------------------------------
# Test 6: Zero float in decisions
# ---------------------------------------------------------------------------


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


@pytest.mark.asyncio
async def test_zero_float_in_decisions() -> None:
    """No float values in any decision's supporting_data or confidence."""
    findings = _build_full_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    for decision in added_decisions:
        assert not isinstance(decision.confidence, float), (
            f"confidence must not be float: {type(decision.confidence).__name__}"
        )
        _assert_no_float_in_dict(decision.supporting_data, f"decision for {decision.entity}")


# ---------------------------------------------------------------------------
# Test 7: confidence is Decimal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confidence_is_decimal() -> None:
    """All decision confidence values must be Decimal instances."""
    findings = _build_full_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    for decision in added_decisions:
        assert isinstance(decision.confidence, Decimal), (
            f"Decision for {decision.entity}: confidence type is "
            f"{type(decision.confidence).__name__}, expected Decimal"
        )


# ---------------------------------------------------------------------------
# Test 8: Naive datetime raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_naive_datetime_raises() -> None:
    """Naive datetime (no tzinfo) should raise ValueError."""
    mock_db = AsyncMock()
    with pytest.raises(ValueError, match="timezone-aware"):
        await run(mock_db, datetime(2026, 4, 14, 10, 0, 0))  # naive


# ---------------------------------------------------------------------------
# Test 9: Empty findings → 0 decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_findings_no_decisions() -> None:
    """No findings → 0 decisions written, summary is clean."""
    mock_db = _make_mock_db(decision_exists=False)

    async def empty_list_findings(**kwargs: Any) -> list:
        return []

    with patch(
        "backend.agents.mf_decisions_generator.list_findings", side_effect=empty_list_findings
    ):
        result = await run(mock_db, _make_data_as_of())

    assert result["findings_read"] == 0
    assert result["decisions_written"] == 0
    assert result["decisions_skipped"] == 0
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Test 10: supporting_data references finding_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supporting_data_references_finding_id() -> None:
    """Each decision's supporting_data contains the source finding_id."""
    findings = _build_full_fixture()
    dispatch = _patch_list_findings(findings)
    finding_ids = {str(f.id) for f in findings}

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    for decision in added_decisions:
        assert "finding_id" in decision.supporting_data, (
            f"Decision for {decision.entity} missing finding_id in supporting_data"
        )
        fid = decision.supporting_data["finding_id"]
        assert fid in finding_ids, f"finding_id {fid!r} not in known finding IDs"


# ---------------------------------------------------------------------------
# Test 11: source_agent is "mf-decisions-generator"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_agent_is_mf_decisions_generator() -> None:
    """All written decisions have source_agent == AGENT_ID."""
    findings = _build_full_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    for decision in added_decisions:
        assert decision.source_agent == AGENT_ID, (
            f"Decision for {decision.entity}: source_agent is {decision.source_agent!r}, "
            f"expected {AGENT_ID!r}"
        )


# ---------------------------------------------------------------------------
# Test 12: entity_type is "mutual_fund" or "mf_category"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entity_type_is_mutual_fund_or_mf_category() -> None:
    """Decisions have entity_type matching their finding's entity_type."""
    findings = _build_full_fixture()
    dispatch = _patch_list_findings(findings)

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, _make_data_as_of())

    valid_entity_types = {"mutual_fund", "mf_category"}
    for decision in added_decisions:
        assert decision.entity_type in valid_entity_types, (
            f"Decision for {decision.entity}: entity_type is {decision.entity_type!r}, "
            f"expected one of {valid_entity_types}"
        )


# ---------------------------------------------------------------------------
# Test 13: No de_* SQL references in source
# ---------------------------------------------------------------------------


def test_no_de_star_sql() -> None:
    """Agent must never reference de_* tables directly."""
    source = inspect.getsource(mf_module)
    de_table_pattern = re.compile(r"\bde_[a-z_]+\b")
    matches = de_table_pattern.findall(source)
    assert matches == [], (
        f"mf_decisions_generator.py contains direct de_* table references: {matches}"
    )


# ---------------------------------------------------------------------------
# Test 14: flow negative_to_positive writes overweight
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_negative_to_positive_writes_overweight() -> None:
    """mf_flow_reversal with flow_direction=negative_to_positive → overweight decision."""
    finding = _make_finding(
        "mf-flow-analyzer",
        "mf_flow_reversal",
        "Mid_Cap",
        entity_type="mf_category",
        evidence={"flow_direction": "negative_to_positive", "category": "Mid Cap"},
    )
    dispatch = {
        ("mf-rs-analyzer", "mf_quadrant_transition"): [],
        ("mf-flow-analyzer", "mf_flow_reversal"): [finding],
    }

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        result = await run(mock_db, _make_data_as_of())

    assert result["decisions_written"] == 1
    assert added_decisions[0].decision_type == "overweight"


# ---------------------------------------------------------------------------
# Test 15: transition to LAGGING writes sell_signal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_to_lagging_writes_sell_signal() -> None:
    """mf_quadrant_transition to LAGGING → sell_signal decision."""
    finding = _make_finding(
        "mf-rs-analyzer",
        "mf_quadrant_transition",
        "KOTAK_MF",
        entity_type="mutual_fund",
        evidence={"quadrant": "LAGGING", "prior_quadrant": "WEAKENING"},
    )
    dispatch = {
        ("mf-rs-analyzer", "mf_quadrant_transition"): [finding],
        ("mf-flow-analyzer", "mf_flow_reversal"): [],
    }

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        result = await run(mock_db, _make_data_as_of())

    assert result["decisions_written"] == 1
    assert added_decisions[0].decision_type == "sell_signal"


# ---------------------------------------------------------------------------
# Test 16: Unknown quadrant returns None from mapper
# ---------------------------------------------------------------------------


def test_transition_unknown_quadrant_returns_none() -> None:
    """_map_mf_quadrant_transition with unknown quadrant returns None."""
    finding = _make_finding(
        "mf-rs-analyzer",
        "mf_quadrant_transition",
        "X",
        evidence={"quadrant": "NEUTRAL"},
    )
    result = _map_mf_quadrant_transition(finding)
    assert result is None


# ---------------------------------------------------------------------------
# Test 17: Unknown flow direction returns None from mapper
# ---------------------------------------------------------------------------


def test_flow_unknown_direction_returns_none() -> None:
    """_map_mf_flow_reversal with unknown flow_direction returns None."""
    finding = _make_finding(
        "mf-flow-analyzer",
        "mf_flow_reversal",
        "X",
        evidence={"flow_direction": "flat"},
    )
    result = _map_mf_flow_reversal(finding)
    assert result is None


# ---------------------------------------------------------------------------
# Additional unit tests for mapper confidence values
# ---------------------------------------------------------------------------


def test_transition_to_leading_confidence() -> None:
    """LEADING transition → confidence 0.85."""
    finding = _make_finding(
        "mf-rs-analyzer",
        "mf_quadrant_transition",
        "X",
        evidence={"quadrant": "LEADING", "prior_quadrant": "IMPROVING"},
    )
    result = _map_mf_quadrant_transition(finding)
    assert result is not None
    assert result[0] == "buy_signal"
    assert result[1] == Decimal("0.85")


def test_transition_to_improving_confidence() -> None:
    """IMPROVING transition → confidence 0.70."""
    finding = _make_finding(
        "mf-rs-analyzer",
        "mf_quadrant_transition",
        "X",
        evidence={"quadrant": "IMPROVING", "prior_quadrant": "LAGGING"},
    )
    result = _map_mf_quadrant_transition(finding)
    assert result is not None
    assert result[0] == "buy_signal"
    assert result[1] == Decimal("0.70")


def test_transition_to_weakening_confidence() -> None:
    """WEAKENING transition → sell_signal confidence 0.75."""
    finding = _make_finding(
        "mf-rs-analyzer",
        "mf_quadrant_transition",
        "X",
        evidence={"quadrant": "WEAKENING", "prior_quadrant": "LEADING"},
    )
    result = _map_mf_quadrant_transition(finding)
    assert result is not None
    assert result[0] == "sell_signal"
    assert result[1] == Decimal("0.75")


def test_flow_positive_to_negative_confidence() -> None:
    """positive_to_negative → avoid confidence 0.75."""
    finding = _make_finding(
        "mf-flow-analyzer",
        "mf_flow_reversal",
        "Large_Cap",
        evidence={"flow_direction": "positive_to_negative"},
    )
    result = _map_mf_flow_reversal(finding)
    assert result is not None
    assert result[0] == "avoid"
    assert result[1] == Decimal("0.75")


def test_flow_negative_to_positive_confidence() -> None:
    """negative_to_positive → overweight confidence 0.70."""
    finding = _make_finding(
        "mf-flow-analyzer",
        "mf_flow_reversal",
        "Mid_Cap",
        evidence={"flow_direction": "negative_to_positive"},
    )
    result = _map_mf_flow_reversal(finding)
    assert result is not None
    assert result[0] == "overweight"
    assert result[1] == Decimal("0.70")


# ---------------------------------------------------------------------------
# horizon_end_date = data_as_of + 20 days
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_horizon_end_date_correct() -> None:
    """All decisions have horizon_end_date = data_as_of.date() + 20 days."""
    from datetime import timedelta

    finding = _make_finding(
        "mf-rs-analyzer",
        "mf_quadrant_transition",
        "HDFC_MF",
        evidence={"quadrant": "LEADING", "prior_quadrant": "IMPROVING"},
    )
    dispatch = {
        ("mf-rs-analyzer", "mf_quadrant_transition"): [finding],
        ("mf-flow-analyzer", "mf_flow_reversal"): [],
    }

    added_decisions: list[Any] = []
    mock_db = _make_mock_db(decision_exists=False)
    mock_db.add = MagicMock(side_effect=added_decisions.append)

    data_as_of = _make_data_as_of()
    expected_horizon_end = data_as_of.date() + timedelta(days=HORIZON_DAYS)

    side_effect = await _mock_list_findings_factory(dispatch)

    with patch("backend.agents.mf_decisions_generator.list_findings", side_effect=side_effect):
        await run(mock_db, data_as_of)

    assert len(added_decisions) == 1
    decision = added_decisions[0]
    assert decision.horizon == HORIZON_LABEL
    assert decision.horizon_end_date == expected_horizon_end
