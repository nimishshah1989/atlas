"""Integration tests for backend/agents/investor_personas.py.

Punch list validation:
1. All 4 personas run on a real trading day (mocked JIP + LLM)
2. Each persona writes ≥1 finding tagged with its persona identifier
3. Each finding has full provenance: evidence contains persona_name, rs_snapshot,
   data_as_of, llm_model
4. LLM calls pass through cost_ledger (record_llm_call is called for each persona)
5. No float values in any financial field
6. No direct de_* SQL in agent source
7. Naive datetime raises ValueError
8. Unknown persona key is skipped gracefully
9. Empty universe produces 0 findings gracefully
10. Per-persona result dict has expected keys: findings_written, stocks_analysed, llm_calls

All DB, JIP, LLM, and cost_ledger calls are mocked — no real API calls.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.investor_personas import (
    ALL_PERSONAS,
    AGENT_TYPE,
    FINDING_PERSONA_ANALYSIS,
    _build_system_prompt,
    _build_user_message,
    _format_stock_data_for_prompt,
    run,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

IST = timezone.utc  # tz-aware; IST detail not needed for unit tests


def _make_data_as_of() -> datetime:
    return datetime(2026, 4, 14, 10, 0, 0, tzinfo=IST)


def _make_universe_fixture() -> list[dict[str, Any]]:
    """5 stocks in the equity universe."""
    return [
        {"symbol": "HDFCBANK", "sector": "Banking"},
        {"symbol": "RELIANCE", "sector": "Energy"},
        {"symbol": "TATASTEEL", "sector": "Metals"},
        {"symbol": "INFY", "sector": "IT"},
        {"symbol": "SUNPHARMA", "sector": "Pharma"},
    ]


def _make_stock_detail(
    symbol: str,
    rs_composite: str,
    rs_momentum: str,
    sector: str = "Banking",
) -> dict[str, Any]:
    """Build a fixture stock detail dict matching JIP get_stock_detail shape."""
    return {
        "symbol": symbol,
        "company_name": f"{symbol} Ltd",
        "sector": sector,
        "rs_composite": Decimal(rs_composite),
        "rs_momentum": Decimal(rs_momentum),
        "rs_1w": Decimal("0.1"),
        "rs_1m": Decimal("0.2"),
        "close": Decimal("1050.00"),
        "rsi_14": Decimal("55.0"),
        "above_200dma": True,
    }


def _make_detail_map() -> dict[str, dict[str, Any]]:
    """Stock detail map: mix of quadrants for realistic data."""
    return {
        "HDFCBANK": _make_stock_detail("HDFCBANK", "0.50", "0.20", "Banking"),  # LEADING
        "RELIANCE": _make_stock_detail("RELIANCE", "0.30", "-0.15", "Energy"),  # WEAKENING
        "TATASTEEL": _make_stock_detail("TATASTEEL", "-0.40", "-0.25", "Metals"),  # LAGGING
        "INFY": _make_stock_detail("INFY", "-0.20", "0.10", "IT"),  # IMPROVING
        "SUNPHARMA": _make_stock_detail("SUNPHARMA", "0.15", "0.05", "Pharma"),  # LEADING
    }


def _make_mock_jip(
    universe: list[dict[str, Any]] | None = None,
    detail_map: dict[str, dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock JIP client returning fixture data."""
    if universe is None:
        universe = _make_universe_fixture()
    if detail_map is None:
        detail_map = _make_detail_map()

    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=universe)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))
    return mock_jip


# ---------------------------------------------------------------------------
# Unit: helper functions
# ---------------------------------------------------------------------------


def test_format_stock_data_for_prompt_non_empty() -> None:
    """_format_stock_data_for_prompt returns a non-empty string for valid stocks."""
    stocks = [
        {
            "symbol": "HDFCBANK",
            "sector": "Banking",
            "rs_composite": "0.50",
            "rs_momentum": "0.20",
            "_quadrant": "LEADING",
        }
    ]
    result = _format_stock_data_for_prompt(stocks)
    assert "HDFCBANK" in result
    assert "LEADING" in result
    assert "Banking" in result


def test_format_stock_data_empty_list() -> None:
    """Empty stocks list returns the no-stocks fallback string."""
    result = _format_stock_data_for_prompt([])
    assert "No stocks available" in result


def test_build_system_prompt_contains_philosophy() -> None:
    """Each persona's system prompt includes its philosophy text."""
    for persona_key in ALL_PERSONAS:
        prompt = _build_system_prompt(persona_key)
        assert len(prompt) > 100, f"System prompt for {persona_key} is too short"
        assert "RS" in prompt


def test_build_user_message_contains_date() -> None:
    """User message includes the formatted data_as_of date."""
    stocks = [
        {
            "symbol": "HDFCBANK",
            "sector": "Banking",
            "rs_composite": "0.50",
            "rs_momentum": "0.20",
            "_quadrant": "LEADING",
        }
    ]
    data_as_of = _make_data_as_of()
    msg = _build_user_message(stocks, data_as_of)
    assert "14-Apr-2026" in msg
    assert "HDFCBANK" in msg


# ---------------------------------------------------------------------------
# Integration: run() — all 4 personas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_all_4_personas_each_writes_finding() -> None:
    """All 4 personas run successfully, each writes ≥1 finding tagged with persona identifier.

    This is the primary punch list test.
    """
    mock_db = AsyncMock()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    stored_calls: list[dict[str, Any]] = []
    llm_call_agent_ids: list[str] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def capture_llm(db: Any, agent_id: str, **kwargs: Any) -> str:
        llm_call_agent_ids.append(agent_id)
        return f"Analysis for {agent_id}: HDFCBANK looks strong in LEADING quadrant."

    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch("backend.agents.investor_personas.complete", side_effect=capture_llm),
    ):
        result = await run(mock_db, mock_jip, data_as_of)

    # Each persona wrote ≥1 finding
    assert result["personas_run"] == 4
    assert result["total_findings_written"] >= 4

    # Each persona made exactly 1 LLM call
    assert len(llm_call_agent_ids) == 4
    for persona_key in ALL_PERSONAS:
        assert f"persona-{persona_key}" in llm_call_agent_ids, (
            f"No LLM call found for persona-{persona_key}"
        )

    # Each finding must be tagged with its persona identifier
    for call_kwargs in stored_calls:
        tags = call_kwargs.get("tags") or []
        # At least one tag should match a known persona key
        persona_tags = [t for t in tags if t in ALL_PERSONAS]
        assert len(persona_tags) >= 1, (
            f"Finding lacks persona tag. Tags: {tags}. Title: {call_kwargs.get('title')}"
        )


@pytest.mark.asyncio
async def test_run_each_finding_has_full_provenance() -> None:
    """Each finding's evidence contains persona_name, data_as_of, llm_model, rs_snapshot."""
    mock_db = AsyncMock()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_llm(db: Any, agent_id: str, **kwargs: Any) -> str:
        return "Mock LLM analysis response."

    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch("backend.agents.investor_personas.complete", side_effect=mock_llm),
    ):
        await run(mock_db, mock_jip, data_as_of)

    assert len(stored_calls) == 4, f"Expected 4 findings (one per persona), got {len(stored_calls)}"

    for call_kwargs in stored_calls:
        evidence = call_kwargs.get("evidence") or {}

        # Full provenance requirements
        assert "persona_name" in evidence, f"Missing persona_name in evidence: {evidence.keys()}"
        assert "data_as_of" in evidence, f"Missing data_as_of in evidence: {evidence.keys()}"
        assert "llm_model" in evidence, f"Missing llm_model in evidence: {evidence.keys()}"
        assert "rs_snapshot" in evidence, f"Missing rs_snapshot in evidence: {evidence.keys()}"

        # rs_snapshot must contain actual RS data
        rs_snapshot = evidence["rs_snapshot"]
        assert isinstance(rs_snapshot, list), f"rs_snapshot must be a list, got {type(rs_snapshot)}"
        assert len(rs_snapshot) > 0, "rs_snapshot must not be empty"

        for entry in rs_snapshot:
            assert "symbol" in entry, f"rs_snapshot entry missing symbol: {entry}"
            assert "rs_composite" in entry, f"rs_snapshot entry missing rs_composite: {entry}"
            assert "rs_momentum" in entry, f"rs_snapshot entry missing rs_momentum: {entry}"
            assert "quadrant" in entry, f"rs_snapshot entry missing quadrant: {entry}"

        # persona_name must be one of the 4 known personas
        assert evidence["persona_name"] in ALL_PERSONAS, (
            f"persona_name '{evidence['persona_name']}' not in ALL_PERSONAS"
        )


@pytest.mark.asyncio
async def test_run_llm_calls_go_through_cost_ledger() -> None:
    """LLM calls pass through the cost ledger — record_llm_call is invoked for each persona."""
    mock_db = AsyncMock()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    cost_ledger_calls: list[dict[str, Any]] = []

    async def mock_record(db: Any, agent_id: str, **kwargs: Any) -> MagicMock:
        cost_ledger_calls.append({"agent_id": agent_id, **kwargs})
        entry = MagicMock()
        entry.id = 1
        return entry

    async def capture_store(**kwargs: Any) -> MagicMock:
        return MagicMock(id="fake-uuid")

    # We patch record_llm_call inside cost_ledger module AND inside llm_client
    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch(
            "backend.services.llm_client.record_llm_call",
            side_effect=mock_record,
        ),
        patch("backend.services.llm_client.httpx.AsyncClient") as mock_http_client,
    ):
        # Mock httpx response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"text": "Mock analysis from LLM."}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(return_value=mock_response))
        )
        mock_http_client.return_value.__aexit__ = AsyncMock(return_value=False)

        import os

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-abc"}):
            result = await run(mock_db, mock_jip, data_as_of)

    # Exactly 4 cost ledger entries — one per persona
    assert len(cost_ledger_calls) == 4, (
        f"Expected 4 cost_ledger entries (one per persona), got {len(cost_ledger_calls)}"
    )

    # Each entry must reference the correct persona agent_id
    recorded_agent_ids = {c["agent_id"] for c in cost_ledger_calls}
    for persona_key in ALL_PERSONAS:
        assert f"persona-{persona_key}" in recorded_agent_ids, (
            f"persona-{persona_key} not in cost ledger agent IDs: {recorded_agent_ids}"
        )

    assert result["total_llm_calls"] == 4


@pytest.mark.asyncio
async def test_run_no_float_in_store_finding_calls() -> None:
    """Verify zero float in any financial field passed to store_finding."""
    mock_db = AsyncMock()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_llm(db: Any, agent_id: str, **kwargs: Any) -> str:
        return "Mock LLM analysis."

    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch("backend.agents.investor_personas.complete", side_effect=mock_llm),
    ):
        await run(mock_db, mock_jip, data_as_of)

    for call_kwargs in stored_calls:
        # confidence must be Decimal
        confidence = call_kwargs.get("confidence")
        assert not isinstance(confidence, float), (
            f"confidence must not be float, got {type(confidence).__name__}: {confidence}"
        )
        assert isinstance(confidence, Decimal), (
            f"confidence must be Decimal, got {type(confidence).__name__}"
        )

        # evidence must not contain raw float values
        evidence = call_kwargs.get("evidence") or {}

        def _check_no_float(d: Any, path: str = "") -> None:
            if isinstance(d, dict):
                for k, v in d.items():
                    _check_no_float(v, f"{path}.{k}")
            elif isinstance(d, list):
                for i, v in enumerate(d):
                    _check_no_float(v, f"{path}[{i}]")
            elif isinstance(d, float):
                raise AssertionError(f"Float found at {path}: {d}")

        _check_no_float(evidence, "evidence")


@pytest.mark.asyncio
async def test_run_naive_datetime_raises() -> None:
    """Naive datetime (no tzinfo) must raise ValueError."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()

    with pytest.raises(ValueError, match="timezone-aware"):
        await run(mock_db, mock_jip, datetime(2026, 4, 14, 10, 0, 0))  # naive


@pytest.mark.asyncio
async def test_run_subset_of_personas() -> None:
    """Can run a subset of personas — only specified ones execute."""
    mock_db = AsyncMock()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    stored_calls: list[dict[str, Any]] = []
    llm_agent_ids: list[str] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_llm(db: Any, agent_id: str, **kwargs: Any) -> str:
        llm_agent_ids.append(agent_id)
        return "Mock analysis."

    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch("backend.agents.investor_personas.complete", side_effect=mock_llm),
    ):
        result = await run(mock_db, mock_jip, data_as_of, personas=["jhunjhunwala", "contrarian"])

    assert result["personas_run"] == 2
    assert result["total_findings_written"] == 2
    assert len(stored_calls) == 2
    assert len(llm_agent_ids) == 2
    assert "persona-jhunjhunwala" in llm_agent_ids
    assert "persona-contrarian" in llm_agent_ids
    assert "persona-value-investor" not in llm_agent_ids


@pytest.mark.asyncio
async def test_run_unknown_persona_key_skipped() -> None:
    """Unknown persona keys are skipped gracefully without raising."""
    mock_db = AsyncMock()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_llm(db: Any, agent_id: str, **kwargs: Any) -> str:
        return "Mock analysis."

    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch("backend.agents.investor_personas.complete", side_effect=mock_llm),
    ):
        # "unknown-persona" is not in _PERSONAS — should be skipped
        result = await run(
            mock_db, mock_jip, data_as_of, personas=["jhunjhunwala", "unknown-persona"]
        )

    assert result["personas_run"] == 1  # only jhunjhunwala ran
    assert result["total_findings_written"] == 1


@pytest.mark.asyncio
async def test_run_empty_universe_produces_zero_findings() -> None:
    """Empty equity universe: 0 findings written, no LLM calls made."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=[])
    data_as_of = _make_data_as_of()

    stored_calls: list[dict[str, Any]] = []
    llm_calls: list[str] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_llm(db: Any, agent_id: str, **kwargs: Any) -> str:
        llm_calls.append(agent_id)
        return "Should not reach here."

    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch("backend.agents.investor_personas.complete", side_effect=mock_llm),
    ):
        result = await run(mock_db, mock_jip, data_as_of)

    assert result["total_findings_written"] == 0
    assert result["total_llm_calls"] == 0
    assert len(stored_calls) == 0
    assert len(llm_calls) == 0


@pytest.mark.asyncio
async def test_run_finding_agent_type_is_llm() -> None:
    """All findings must have agent_type = 'llm'."""
    mock_db = AsyncMock()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_llm(db: Any, agent_id: str, **kwargs: Any) -> str:
        return "Analysis."

    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch("backend.agents.investor_personas.complete", side_effect=mock_llm),
    ):
        await run(mock_db, mock_jip, data_as_of)

    for call_kwargs in stored_calls:
        assert call_kwargs["agent_type"] == AGENT_TYPE, (
            f"Expected agent_type='llm', got '{call_kwargs['agent_type']}'"
        )


@pytest.mark.asyncio
async def test_run_finding_type_is_persona_analysis() -> None:
    """All findings must have finding_type = 'persona_analysis'."""
    mock_db = AsyncMock()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_llm(db: Any, agent_id: str, **kwargs: Any) -> str:
        return "Analysis."

    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch("backend.agents.investor_personas.complete", side_effect=mock_llm),
    ):
        await run(mock_db, mock_jip, data_as_of)

    for call_kwargs in stored_calls:
        assert call_kwargs["finding_type"] == FINDING_PERSONA_ANALYSIS, (
            f"Expected finding_type='persona_analysis', got '{call_kwargs['finding_type']}'"
        )


@pytest.mark.asyncio
async def test_run_zero_de_star_sql_in_agent() -> None:
    """Agent must never reference de_* tables directly — only JIP client methods."""
    import inspect

    import backend.agents.investor_personas as module

    source = inspect.getsource(module)
    de_table_pattern = re.compile(r"\bde_[a-z_]+\b")
    matches = de_table_pattern.findall(source)
    assert matches == [], (
        f"investor_personas.py contains direct de_* table references: {matches}. "
        "Use JIPDataService methods only."
    )


@pytest.mark.asyncio
async def test_run_per_persona_result_dict_has_expected_keys() -> None:
    """Per-persona result dicts must have findings_written, stocks_analysed, llm_calls."""
    mock_db = AsyncMock()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    async def capture_store(**kwargs: Any) -> MagicMock:
        return MagicMock(id="fake-uuid")

    async def mock_llm(db: Any, agent_id: str, **kwargs: Any) -> str:
        return "Analysis."

    with (
        patch("backend.agents.investor_personas.store_finding", side_effect=capture_store),
        patch("backend.agents.investor_personas.complete", side_effect=mock_llm),
    ):
        result = await run(mock_db, mock_jip, data_as_of)

    per_persona = result["per_persona"]
    assert len(per_persona) == 4

    for persona_key in ALL_PERSONAS:
        assert persona_key in per_persona, f"Missing per_persona entry for {persona_key}"
        pr = per_persona[persona_key]
        assert "findings_written" in pr, f"Missing findings_written for {persona_key}"
        assert "stocks_analysed" in pr, f"Missing stocks_analysed for {persona_key}"
        assert "llm_calls" in pr, f"Missing llm_calls for {persona_key}"
        assert pr["findings_written"] == 1
        assert pr["stocks_analysed"] > 0
        assert pr["llm_calls"] == 1
