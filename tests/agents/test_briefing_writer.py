"""Integration tests for backend/agents/briefing_writer.py.

Punch list validation:
(a) exactly one atlas_briefings row per trading day after one run (upsert called once)
(b) rerun updates in place, not duplicates (ON CONFLICT DO UPDATE semantics verified)
(c) same data_as_of → identical key_signals/theses/conviction/model_used (deterministic)
(d) missing upstream source still produces a briefing with staleness flag

Additional tests:
5. _sanitize_for_jsonb handles Decimal values in dicts
6. store_finding called (companion intelligence finding)

All DB, JIP, LLM calls are mocked — no real API calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.briefing_writer import (
    AGENT_ID,
    CONVICTION_LEVELS,
    EDITOR_MODEL,
    _parse_conviction,
    _parse_editor_response,
    run,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

IST = timezone.utc  # tz-aware; exact tz not needed for unit tests


def _make_data_as_of() -> datetime:
    return datetime(2026, 4, 14, 9, 0, 0, tzinfo=IST)


def _make_valid_editor_json(
    key_signals: list[str] | None = None,
    theses: list[str] | None = None,
) -> str:
    """Return a valid JSON string matching the editor schema."""
    return json.dumps(
        {
            "headline": "Markets steady as macro cues stabilise",
            "narrative": "Indian equity markets opened on a steady note...",
            "key_signals": key_signals or ["FII inflows positive", "Nifty above 200 DMA"],
            "theses": theses or ["IT sector re-rating possible", "Banks look cheap"],
            "patterns": ["Bull flag on Nifty", "RSI neutral"],
            "india_implication": "Domestic consumption themes remain resilient.",
            "risk_scenario": "Sharp crude spike could pressure margins.",
        }
    )


def _make_mock_db() -> AsyncMock:
    """Build a mock async DB session."""
    mock_db = AsyncMock()
    # Mock execute to return an empty result set (no upstream findings)
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=execute_result)
    mock_db.commit = AsyncMock()
    return mock_db


def _make_mock_db_with_findings(findings: list[MagicMock]) -> AsyncMock:
    """Build a mock DB with upstream intelligence findings."""
    mock_db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = findings
    mock_db.execute = AsyncMock(return_value=execute_result)
    mock_db.commit = AsyncMock()
    return mock_db


def _make_fake_finding(title: str, content: str, finding_type: str = "rs_analysis") -> MagicMock:
    """Build a fake AtlasIntelligence row."""
    f = MagicMock()
    f.finding_type = finding_type
    f.title = title
    f.content = content
    return f


def _make_mock_jip() -> AsyncMock:
    mock_jip = AsyncMock()
    mock_jip.get_equity_universe = AsyncMock(return_value=[])
    return mock_jip


_LLM_CALL_COUNT = 0


def _make_llm_side_effect(
    perspective_text: str = "Macro looks stable for Indian markets.",
    judge_text: str = "bull\nPositive macro backdrop supports equities.",
    editor_json: str | None = None,
) -> Any:
    """Returns a side_effect function that cycles through LLM call types."""
    if editor_json is None:
        editor_json = _make_valid_editor_json()

    call_count = [0]

    async def _llm_side_effect(
        db: Any,
        agent_id: str,
        system_prompt: str,
        user_message: str,
        model: str = "claude-haiku-4-5-20251001",
        **kwargs: Any,
    ) -> str:
        call_count[0] += 1
        n = call_count[0]
        if n <= 4:
            # Sub-agent perspectives
            return perspective_text
        elif n == 5:
            # Debate judge
            return judge_text
        else:
            # Editor synthesis
            return editor_json

    return _llm_side_effect


# ---------------------------------------------------------------------------
# Test 1: exactly one upsert per trading day
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_produces_one_briefing_per_day() -> None:
    """Run once — exactly 1 upsert call to atlas_briefings for the given date."""
    mock_db = _make_mock_db()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    async def capture_store(**kwargs: Any) -> MagicMock:
        return MagicMock(id="fake-uuid")

    with (
        patch("backend.agents.briefing_writer.complete", side_effect=_make_llm_side_effect()),
        patch("backend.agents.briefing_writer.store_finding", side_effect=capture_store),
    ):
        result = await run(mock_db, mock_jip, data_as_of)

    # db.execute was called: once for SELECT (upstream findings) + once for upsert
    # Verify exactly one execute call had the INSERT ON CONFLICT SQL
    all_execute_calls = mock_db.execute.call_args_list
    upsert_sql_calls = [
        c for c in all_execute_calls if c.args and "INSERT INTO atlas_briefings" in str(c.args[0])
    ]
    assert len(upsert_sql_calls) == 1, (
        f"Expected exactly 1 upsert call to atlas_briefings, got {len(upsert_sql_calls)}"
    )

    # Result must include expected fields
    assert result["briefing_date"] == data_as_of.date().isoformat()
    assert result["scope"] == "market"
    assert result["model_used"] == EDITOR_MODEL
    assert result["llm_calls"] == 6


# ---------------------------------------------------------------------------
# Test 2: rerun updates in place (idempotent)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerun_updates_in_place() -> None:
    """Run twice with same data_as_of — upsert (ON CONFLICT DO UPDATE) called both times.

    The SQL must include ON CONFLICT ... DO UPDATE, not two plain INSERTs.
    """
    mock_db = _make_mock_db()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    stored_findings: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_findings.append(kwargs)
        return MagicMock(id="fake-uuid")

    all_execute_sqls: list[str] = []

    original_execute = mock_db.execute

    async def capturing_execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        all_execute_sqls.append(str(stmt))
        return await original_execute(stmt, *args, **kwargs)

    mock_db.execute = capturing_execute

    with (
        patch("backend.agents.briefing_writer.complete", side_effect=_make_llm_side_effect()),
        patch("backend.agents.briefing_writer.store_finding", side_effect=capture_store),
    ):
        await run(mock_db, mock_jip, data_as_of)

    # Reset for second run
    mock_db2 = _make_mock_db()
    all_execute_sqls2: list[str] = []
    original_execute2 = mock_db2.execute

    async def capturing_execute2(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        all_execute_sqls2.append(str(stmt))
        return await original_execute2(stmt, *args, **kwargs)

    mock_db2.execute = capturing_execute2

    with (
        patch("backend.agents.briefing_writer.complete", side_effect=_make_llm_side_effect()),
        patch("backend.agents.briefing_writer.store_finding", side_effect=capture_store),
    ):
        await run(mock_db2, mock_jip, data_as_of)

    # Both runs must include ON CONFLICT DO UPDATE in their upsert SQL
    for run_sqls in (all_execute_sqls, all_execute_sqls2):
        upsert_sqls = [s for s in run_sqls if "INSERT INTO atlas_briefings" in s]
        assert len(upsert_sqls) >= 1, "Expected upsert SQL in run"
        assert any("ON CONFLICT" in s for s in upsert_sqls), (
            "Upsert SQL must contain ON CONFLICT clause"
        )
        assert any("DO UPDATE" in s for s in upsert_sqls), (
            "Upsert SQL must contain DO UPDATE clause"
        )


# ---------------------------------------------------------------------------
# Test 3: deterministic output for same data_as_of
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deterministic_output() -> None:
    """Same data_as_of + same mocked LLM → same key_signals, theses, conviction, model_used."""
    data_as_of = _make_data_as_of()

    # Use fixed LLM responses for both runs
    fixed_key_signals = ["Signal A", "Signal B"]
    fixed_theses = ["Thesis X", "Thesis Y"]
    fixed_editor_json = _make_valid_editor_json(
        key_signals=fixed_key_signals,
        theses=fixed_theses,
    )
    fixed_judge = "bull\nFixed ruling for determinism test."

    async def capture_store(**kwargs: Any) -> MagicMock:
        return MagicMock(id="fake-uuid")

    results: list[dict[str, Any]] = []
    all_upsert_params: list[dict[str, Any]] = []

    for _ in range(2):
        mock_db = _make_mock_db()
        mock_jip = _make_mock_jip()

        upsert_params_for_run: list[dict[str, Any]] = []
        original_execute = mock_db.execute

        async def capturing_execute(
            stmt: Any,
            params: Any = None,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            if params and isinstance(params, dict) and "conviction" in params:
                upsert_params_for_run.append(dict(params))
            return await original_execute(stmt, params, *args, **kwargs)

        mock_db.execute = capturing_execute

        with (
            patch(
                "backend.agents.briefing_writer.complete",
                side_effect=_make_llm_side_effect(
                    judge_text=fixed_judge,
                    editor_json=fixed_editor_json,
                ),
            ),
            patch("backend.agents.briefing_writer.store_finding", side_effect=capture_store),
        ):
            r = await run(mock_db, mock_jip, data_as_of)
            results.append(r)
            all_upsert_params.append(upsert_params_for_run[0] if upsert_params_for_run else {})

    # Both runs must produce identical conviction and model_used
    assert results[0]["conviction"] == results[1]["conviction"], (
        f"conviction differs: {results[0]['conviction']} vs {results[1]['conviction']}"
    )
    assert results[0]["model_used"] == results[1]["model_used"], (
        f"model_used differs: {results[0]['model_used']} vs {results[1]['model_used']}"
    )

    # key_signals and theses in upsert params must match
    if all_upsert_params[0] and all_upsert_params[1]:
        assert all_upsert_params[0].get("key_signals") == all_upsert_params[1].get("key_signals"), (
            "key_signals differ between runs"
        )
        assert all_upsert_params[0].get("theses") == all_upsert_params[1].get("theses"), (
            "theses differ between runs"
        )


# ---------------------------------------------------------------------------
# Test 4: missing upstream produces staleness flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_upstream_produces_staleness_flag() -> None:
    """No upstream intelligence findings → briefing still produced with staleness_flags set."""
    # Empty DB (no findings) — already the default in _make_mock_db()
    mock_db = _make_mock_db()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    upsert_params: list[dict[str, Any]] = []
    original_execute = mock_db.execute

    async def capturing_execute(
        stmt: Any,
        params: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if params and isinstance(params, dict) and "staleness_flags" in params:
            upsert_params.append(dict(params))
        return await original_execute(stmt, params, *args, **kwargs)

    mock_db.execute = capturing_execute

    async def capture_store(**kwargs: Any) -> MagicMock:
        return MagicMock(id="fake-uuid")

    with (
        patch("backend.agents.briefing_writer.complete", side_effect=_make_llm_side_effect()),
        patch("backend.agents.briefing_writer.store_finding", side_effect=capture_store),
    ):
        result = await run(mock_db, mock_jip, data_as_of)

    # Result must have staleness_flags populated
    assert result["staleness_flags"] is not None, "staleness_flags must be set when no upstream"
    assert result["upstream_findings_used"] == 0

    # Upsert params should contain staleness_flags JSON with upstream key
    if upsert_params:
        sf_raw = upsert_params[0].get("staleness_flags", "null")
        sf = json.loads(sf_raw) if isinstance(sf_raw, str) else sf_raw
        if sf:
            assert "upstream" in sf, f"staleness_flags missing 'upstream' key: {sf}"


# ---------------------------------------------------------------------------
# Test 5: _sanitize_for_jsonb handles Decimal
# ---------------------------------------------------------------------------


def test_sanitize_for_jsonb_converts_decimal() -> None:
    """Decimal values in evidence dicts are converted to str for JSONB compatibility."""
    from backend.services.intelligence import _sanitize_for_jsonb

    evidence: dict[str, Any] = {
        "confidence": Decimal("0.75"),
        "nested": {"value": Decimal("1234.5678")},
        "plain_str": "hello",
        "plain_int": 42,
        "list_field": [Decimal("0.1"), "text", 99],
    }
    sanitized = _sanitize_for_jsonb(evidence)

    assert isinstance(sanitized["confidence"], str), "Decimal must become str"
    assert sanitized["confidence"] == "0.75"
    assert isinstance(sanitized["nested"]["value"], str), "Nested Decimal must become str"
    assert sanitized["nested"]["value"] == "1234.5678"
    assert sanitized["plain_str"] == "hello"
    assert sanitized["plain_int"] == 42
    assert sanitized["list_field"][0] == "0.1"  # Decimal in list → str
    assert sanitized["list_field"][1] == "text"
    assert sanitized["list_field"][2] == 99


# ---------------------------------------------------------------------------
# Test 6: store_finding called (companion intelligence finding)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_briefing_also_writes_intelligence_finding() -> None:
    """store_finding is called once to write the companion intelligence finding."""
    mock_db = _make_mock_db()
    mock_jip = _make_mock_jip()
    data_as_of = _make_data_as_of()

    store_finding_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        store_finding_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with (
        patch("backend.agents.briefing_writer.complete", side_effect=_make_llm_side_effect()),
        patch("backend.agents.briefing_writer.store_finding", side_effect=capture_store),
    ):
        await run(mock_db, mock_jip, data_as_of)

    assert len(store_finding_calls) == 1, (
        f"Expected 1 store_finding call, got {len(store_finding_calls)}"
    )
    sf = store_finding_calls[0]
    assert sf["agent_id"] == AGENT_ID
    assert sf["agent_type"] == "llm"
    assert sf["finding_type"] == "morning_briefing"
    assert isinstance(sf["confidence"], Decimal), "confidence must be Decimal"
    assert "briefing" in sf.get("tags", [])


# ---------------------------------------------------------------------------
# Additional: parse helpers
# ---------------------------------------------------------------------------


def test_parse_conviction_valid_levels() -> None:
    """_parse_conviction extracts valid conviction levels from judge response."""
    for level in CONVICTION_LEVELS:
        conviction, ruling = _parse_conviction(f"{level}\nSome ruling text here.")
        assert conviction == level, f"Expected {level}, got {conviction}"
        assert "Some ruling text" in ruling


def test_parse_conviction_fallback_to_neutral() -> None:
    """_parse_conviction falls back to 'neutral' for unrecognised responses."""
    conviction, _ = _parse_conviction("I cannot determine the direction.")
    assert conviction == "neutral"


def test_parse_editor_response_valid_json() -> None:
    """_parse_editor_response returns structured dict from valid JSON."""
    raw = _make_valid_editor_json(
        key_signals=["Signal A"],
        theses=["Thesis B"],
    )
    result = _parse_editor_response(raw)
    assert result["headline"] == "Markets steady as macro cues stabilise"
    assert result["key_signals"] == ["Signal A"]
    assert result["theses"] == ["Thesis B"]
    assert result["narrative"] == "Indian equity markets opened on a steady note..."


def test_parse_editor_response_invalid_json_fallback() -> None:
    """_parse_editor_response falls back gracefully on non-JSON input."""
    raw = "This is not JSON at all. Just plain text analysis."
    result = _parse_editor_response(raw)
    assert result["narrative"] == raw
    assert result["headline"] == "Indian Equity Market Morning Briefing"
    assert result["key_signals"] == []
    assert result["theses"] == []


def test_parse_editor_response_strips_markdown_fences() -> None:
    """_parse_editor_response handles JSON wrapped in markdown code fences."""
    raw = "```json\n" + _make_valid_editor_json() + "\n```"
    result = _parse_editor_response(raw)
    assert result["headline"] == "Markets steady as macro cues stabilise"


@pytest.mark.asyncio
async def test_run_naive_datetime_raises() -> None:
    """Naive datetime (no tzinfo) must raise ValueError."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()

    with pytest.raises(ValueError, match="timezone-aware"):
        await run(mock_db, mock_jip, datetime(2026, 4, 14, 9, 0, 0))  # naive
