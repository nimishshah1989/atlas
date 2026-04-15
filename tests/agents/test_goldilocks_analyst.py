"""Unit tests for backend/agents/goldilocks_analyst.py.

Punch list validation:
1. ≥5 real Goldilocks ideas produce ≥5 findings with evidence pointing to both
   Goldilocks source row and RS data
2. Missing-ticker path logs a data gap without aborting (continues to next idea)
3. Naive datetime raises ValueError
4. No float values in any store_finding call (all Decimal)
5. Empty stock ideas list: only summary written
6. Zero de_* SQL in agent source code — only JIP client methods
7. Non-BUY actions (SELL, HOLD, WATCH) are skipped
8. Each finding evidence contains both goldilocks_symbol and rs_quadrant keys

All DB, JIP, and embedding calls are mocked — no real DB or API calls.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.goldilocks_analyst import (
    AGENT_ID,
    AGENT_TYPE,
    FINDING_ALIGNMENT,
    FINDING_DIVERGENCE,
    FINDING_NEUTRAL,
    FINDING_SUMMARY,
    _is_buy_action,
    _safe_decimal,
    run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

IST = timezone.utc  # tz-aware; IST detail not needed for unit tests


def _make_data_as_of() -> datetime:
    return datetime(2026, 4, 14, 10, 0, 0, tzinfo=IST)


def _make_idea(
    symbol: str,
    action: str = "BUY",
    entry_price: str = "1000.00",
    target_price: str = "1200.00",
    stop_loss: str = "900.00",
    rationale: str = "Strong fundamentals",
    idea_date: str = "2026-04-14",
    sector: str = "Banking",
) -> dict[str, Any]:
    """Build a fixture Goldilocks stock idea dict."""
    return {
        "symbol": symbol,
        "action": action,
        "entry_price": Decimal(entry_price),
        "target_price": Decimal(target_price),
        "stop_loss": Decimal(stop_loss),
        "rationale": rationale,
        "idea_date": idea_date,
        "sector": sector,
        "confidence": None,
    }


def _make_stock_detail(
    symbol: str,
    rs_composite: str,
    rs_momentum: str,
) -> dict[str, Any]:
    """Build a fixture stock detail dict matching JIP get_stock_detail shape."""
    return {
        "symbol": symbol,
        "company_name": f"{symbol} Ltd",
        "sector": "Banking",
        "rs_composite": Decimal(rs_composite),
        "rs_momentum": Decimal(rs_momentum),
        "rs_1w": Decimal("0.1"),
        "rs_1m": Decimal("0.2"),
        "close": Decimal("1050.00"),
        "rsi_14": Decimal("55.0"),
        "above_200dma": True,
    }


def _build_5_idea_fixture() -> list[dict[str, Any]]:
    """5 Goldilocks ideas with varied RS alignments.

    - HDFCBANK: BUY + LEADING (rs_composite > 0, rs_momentum > 0) → alignment
    - ICICIBANK: BUY + LEADING → alignment
    - TATASTEEL: BUY + LAGGING (rs_composite < 0, rs_momentum < 0) → divergence
    - INFY: BUY + IMPROVING (rs_composite < 0, rs_momentum > 0) → neutral
    - RELIANCE: BUY + WEAKENING (rs_composite > 0, rs_momentum < 0) → neutral
    """
    return [
        _make_idea("HDFCBANK"),
        _make_idea("ICICIBANK"),
        _make_idea("TATASTEEL"),
        _make_idea("INFY"),
        _make_idea("RELIANCE"),
    ]


def _build_stock_detail_map() -> dict[str, dict[str, Any]]:
    return {
        "HDFCBANK": _make_stock_detail("HDFCBANK", "0.50", "0.20"),  # LEADING
        "ICICIBANK": _make_stock_detail("ICICIBANK", "0.30", "0.15"),  # LEADING
        "TATASTEEL": _make_stock_detail("TATASTEEL", "-0.40", "-0.25"),  # LAGGING
        "INFY": _make_stock_detail("INFY", "-0.20", "0.10"),  # IMPROVING
        "RELIANCE": _make_stock_detail("RELIANCE", "0.15", "-0.30"),  # WEAKENING
    }


async def _mock_get_stock_detail(
    detail_map: dict[str, dict[str, Any]],
) -> Any:
    """Factory returning an AsyncMock that looks up symbols in detail_map."""

    async def _get(symbol: str) -> dict[str, Any] | None:
        return detail_map.get(symbol)

    return _get


# ---------------------------------------------------------------------------
# Unit: _is_buy_action
# ---------------------------------------------------------------------------


def test_is_buy_action_buy() -> None:
    assert _is_buy_action("BUY") is True


def test_is_buy_action_strong_buy() -> None:
    assert _is_buy_action("STRONG BUY") is True


def test_is_buy_action_accumulate() -> None:
    assert _is_buy_action("ACCUMULATE") is True


def test_is_buy_action_add() -> None:
    assert _is_buy_action("ADD") is True


def test_is_buy_action_sell_is_false() -> None:
    assert _is_buy_action("SELL") is False


def test_is_buy_action_hold_is_false() -> None:
    assert _is_buy_action("HOLD") is False


def test_is_buy_action_watch_is_false() -> None:
    assert _is_buy_action("WATCH") is False


def test_is_buy_action_none_is_false() -> None:
    assert _is_buy_action(None) is False


def test_is_buy_action_empty_is_false() -> None:
    assert _is_buy_action("") is False


# ---------------------------------------------------------------------------
# Unit: _safe_decimal
# ---------------------------------------------------------------------------


def test_safe_decimal_from_decimal() -> None:
    assert _safe_decimal(Decimal("123.45"), "price") == Decimal("123.45")


def test_safe_decimal_from_str() -> None:
    assert _safe_decimal("456.78", "price") == Decimal("456.78")


def test_safe_decimal_from_int() -> None:
    assert _safe_decimal(100, "price") == Decimal("100")


def test_safe_decimal_none_returns_none() -> None:
    assert _safe_decimal(None, "price") is None


def test_safe_decimal_invalid_returns_none() -> None:
    # "abc" is not a valid Decimal
    result = _safe_decimal("abc", "price")
    assert result is None


# ---------------------------------------------------------------------------
# Integration-style: run() with mocked DB + JIP + store_finding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_5_ideas_produces_5_findings_with_evidence() -> None:
    """Main punch list test: 5 Goldilocks ideas → 5 findings + 1 summary.

    Each finding's evidence must contain both goldilocks_symbol and rs_quadrant.
    """
    ideas = _build_5_idea_fixture()
    detail_map = _build_stock_detail_map()

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=ideas)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with patch("backend.agents.goldilocks_analyst.store_finding", side_effect=capture_store):
        await run(mock_db, mock_jip, _make_data_as_of())

    # 5 idea findings + 1 summary
    non_summary = [c for c in stored_calls if c.get("finding_type") != FINDING_SUMMARY]
    summary_calls = [c for c in stored_calls if c.get("finding_type") == FINDING_SUMMARY]

    assert len(non_summary) >= 5, f"Expected ≥5 idea findings, got {len(non_summary)}"
    assert len(summary_calls) == 1, "Expected exactly 1 summary finding"

    # Each idea finding must have evidence pointing to both sources
    for call in non_summary:
        evidence = call.get("evidence") or {}
        assert "goldilocks_symbol" in evidence, (
            f"Missing goldilocks_symbol in evidence for finding {call.get('title')}"
        )
        assert "rs_quadrant" in evidence, (
            f"Missing rs_quadrant in evidence for finding {call.get('title')}"
        )
        assert "goldilocks_action" in evidence, (
            f"Missing goldilocks_action in evidence for finding {call.get('title')}"
        )
        assert "rs_composite" in evidence, (
            f"Missing rs_composite in evidence for finding {call.get('title')}"
        )


@pytest.mark.asyncio
async def test_run_5_ideas_correct_finding_types() -> None:
    """2 LEADING → alignment, 1 LAGGING → divergence, 2 IMPROVING/WEAKENING → neutral."""
    ideas = _build_5_idea_fixture()
    detail_map = _build_stock_detail_map()

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=ideas)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with patch("backend.agents.goldilocks_analyst.store_finding", side_effect=capture_store):
        result = await run(mock_db, mock_jip, _make_data_as_of())

    alignment_calls = [c for c in stored_calls if c.get("finding_type") == FINDING_ALIGNMENT]
    divergence_calls = [c for c in stored_calls if c.get("finding_type") == FINDING_DIVERGENCE]
    neutral_calls = [c for c in stored_calls if c.get("finding_type") == FINDING_NEUTRAL]

    assert len(alignment_calls) == 2, f"Expected 2 alignment findings, got {len(alignment_calls)}"
    assert len(divergence_calls) == 1, f"Expected 1 divergence finding, got {len(divergence_calls)}"
    assert len(neutral_calls) == 2, f"Expected 2 neutral findings, got {len(neutral_calls)}"

    assert result["alignments"] == 2
    assert result["divergences"] == 1
    assert result["neutrals"] == 2
    assert result["analyzed"] == 5


@pytest.mark.asyncio
async def test_run_missing_ticker_logs_gap_does_not_abort() -> None:
    """Missing ticker (get_stock_detail returns None) logs warning and continues."""
    ideas = _build_5_idea_fixture() + [_make_idea("MISSING_TICKER")]
    detail_map = _build_stock_detail_map()
    # MISSING_TICKER is not in detail_map — get_stock_detail returns None

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=ideas)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with patch("backend.agents.goldilocks_analyst.store_finding", side_effect=capture_store):
        # Must not raise — missing ticker is handled gracefully
        result = await run(mock_db, mock_jip, _make_data_as_of())

    # Should still produce 5 findings for the valid ideas + 1 summary
    non_summary = [c for c in stored_calls if c.get("finding_type") != FINDING_SUMMARY]
    assert len(non_summary) == 5, (
        f"Expected 5 idea findings (6 ideas, 1 missing), got {len(non_summary)}"
    )

    # Missing ticker tracked in result
    assert result["missing_tickers"] == 1, (
        f"Expected 1 missing ticker, got {result['missing_tickers']}"
    )

    # Summary finding counts missing_tickers
    summary_call = next(c for c in stored_calls if c.get("finding_type") == FINDING_SUMMARY)
    assert summary_call["evidence"]["missing_tickers"] == 1


@pytest.mark.asyncio
async def test_run_naive_datetime_raises() -> None:
    """Naive datetime (no tzinfo) must raise ValueError."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()

    with pytest.raises(ValueError, match="timezone-aware"):
        await run(mock_db, mock_jip, datetime(2026, 4, 14, 10, 0, 0))  # naive


@pytest.mark.asyncio
async def test_run_no_float_in_store_finding_calls() -> None:
    """Verify zero float in any financial field passed to store_finding."""
    ideas = _build_5_idea_fixture()
    detail_map = _build_stock_detail_map()

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=ideas)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with patch("backend.agents.goldilocks_analyst.store_finding", side_effect=capture_store):
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
        float_fields = [k for k, v in evidence.items() if isinstance(v, float)]
        assert float_fields == [], (
            f"Float values found in evidence for '{call_kwargs.get('title')}': {float_fields}"
        )


@pytest.mark.asyncio
async def test_run_empty_ideas_writes_only_summary() -> None:
    """Empty stock ideas list: only summary written, analyzed=0."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=[])

    with patch(
        "backend.agents.goldilocks_analyst.store_finding", new_callable=AsyncMock
    ) as mock_store:
        mock_store.return_value = MagicMock(id="fake-uuid")
        result = await run(mock_db, mock_jip, _make_data_as_of())

    assert result["analyzed"] == 0
    assert result["alignments"] == 0
    assert result["divergences"] == 0
    assert result["neutrals"] == 0
    assert result["findings_written"] == 1  # only summary
    assert mock_store.call_count == 1

    # The one call must be the summary
    call_kwargs = mock_store.call_args.kwargs
    assert call_kwargs["finding_type"] == FINDING_SUMMARY
    assert call_kwargs["entity"] == "market"
    assert call_kwargs["entity_type"] == "summary"


@pytest.mark.asyncio
async def test_run_non_buy_actions_skipped() -> None:
    """SELL, HOLD, WATCH actions are skipped; no finding written for them."""
    ideas = [
        _make_idea("SBIN", action="SELL"),
        _make_idea("ONGC", action="HOLD"),
        _make_idea("WIPRO", action="WATCH"),
        _make_idea("HDFCBANK", action="BUY"),  # only this one processed
    ]
    detail_map = {"HDFCBANK": _make_stock_detail("HDFCBANK", "0.50", "0.20")}

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=ideas)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with patch("backend.agents.goldilocks_analyst.store_finding", side_effect=capture_store):
        result = await run(mock_db, mock_jip, _make_data_as_of())

    non_summary = [c for c in stored_calls if c.get("finding_type") != FINDING_SUMMARY]
    assert len(non_summary) == 1, (
        f"Only HDFCBANK BUY should produce a finding, got {len(non_summary)}"
    )
    assert non_summary[0]["entity"] == "HDFCBANK"
    assert result["analyzed"] == 1


@pytest.mark.asyncio
async def test_run_zero_de_star_sql_in_agent() -> None:
    """Agent must never reference de_* tables directly — only JIP client methods."""
    import inspect

    import backend.agents.goldilocks_analyst as module

    source = inspect.getsource(module)
    de_table_pattern = re.compile(r"\bde_[a-z_]+\b")
    matches = de_table_pattern.findall(source)
    assert matches == [], (
        f"goldilocks_analyst.py contains direct de_* table references: {matches}. "
        "Use JIPDataService methods only."
    )


@pytest.mark.asyncio
async def test_run_summary_entity_is_market() -> None:
    """Summary finding must have entity='market', entity_type='summary', agent_id=AGENT_ID."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=[])

    with patch(
        "backend.agents.goldilocks_analyst.store_finding", new_callable=AsyncMock
    ) as mock_store:
        mock_store.return_value = MagicMock(id="fake-uuid")
        await run(mock_db, mock_jip, _make_data_as_of())

    last_call_kwargs = mock_store.call_args_list[-1].kwargs
    assert last_call_kwargs["entity"] == "market"
    assert last_call_kwargs["entity_type"] == "summary"
    assert last_call_kwargs["finding_type"] == FINDING_SUMMARY
    assert last_call_kwargs["agent_id"] == AGENT_ID
    assert last_call_kwargs["agent_type"] == AGENT_TYPE


@pytest.mark.asyncio
async def test_run_alignment_finding_content_mentions_aligns() -> None:
    """BUY + LEADING finding title must contain 'aligns'."""
    ideas = [_make_idea("HDFCBANK", action="BUY")]
    detail_map = {"HDFCBANK": _make_stock_detail("HDFCBANK", "0.50", "0.20")}  # LEADING

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=ideas)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with patch("backend.agents.goldilocks_analyst.store_finding", side_effect=capture_store):
        await run(mock_db, mock_jip, _make_data_as_of())

    alignment_call = next(c for c in stored_calls if c.get("finding_type") == FINDING_ALIGNMENT)
    assert "aligns" in alignment_call["title"].lower(), (
        f"Alignment title must mention 'aligns', got: {alignment_call['title']}"
    )


@pytest.mark.asyncio
async def test_run_divergence_finding_content_mentions_divergent() -> None:
    """BUY + LAGGING finding title must contain 'DIVERGENT SIGNAL'."""
    ideas = [_make_idea("TATASTEEL", action="BUY")]
    detail_map = {"TATASTEEL": _make_stock_detail("TATASTEEL", "-0.40", "-0.25")}  # LAGGING

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=ideas)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with patch("backend.agents.goldilocks_analyst.store_finding", side_effect=capture_store):
        await run(mock_db, mock_jip, _make_data_as_of())

    divergence_call = next(c for c in stored_calls if c.get("finding_type") == FINDING_DIVERGENCE)
    assert "DIVERGENT SIGNAL" in divergence_call["title"], (
        f"Divergence title must contain 'DIVERGENT SIGNAL', got: {divergence_call['title']}"
    )


@pytest.mark.asyncio
async def test_run_evidence_alignment_field() -> None:
    """Evidence must contain 'alignment' key with correct value per finding type."""
    ideas = [
        _make_idea("HDFCBANK"),  # LEADING → ALIGNED
        _make_idea("TATASTEEL"),  # LAGGING → DIVERGENT
        _make_idea("INFY"),  # IMPROVING → NEUTRAL
    ]
    detail_map = {
        "HDFCBANK": _make_stock_detail("HDFCBANK", "0.50", "0.20"),
        "TATASTEEL": _make_stock_detail("TATASTEEL", "-0.40", "-0.25"),
        "INFY": _make_stock_detail("INFY", "-0.20", "0.10"),
    }

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=ideas)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with patch("backend.agents.goldilocks_analyst.store_finding", side_effect=capture_store):
        await run(mock_db, mock_jip, _make_data_as_of())

    align_call = next(c for c in stored_calls if c.get("finding_type") == FINDING_ALIGNMENT)
    div_call = next(c for c in stored_calls if c.get("finding_type") == FINDING_DIVERGENCE)
    neutral_call = next(c for c in stored_calls if c.get("finding_type") == FINDING_NEUTRAL)

    assert align_call["evidence"]["alignment"] == "ALIGNED"
    assert div_call["evidence"]["alignment"] == "DIVERGENT"
    assert neutral_call["evidence"]["alignment"] == "NEUTRAL"


@pytest.mark.asyncio
async def test_run_idempotent() -> None:
    """Same data as_of produces same store_finding call count on second run."""
    ideas = _build_5_idea_fixture()
    detail_map = _build_stock_detail_map()

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_goldilocks_stock_ideas = AsyncMock(return_value=ideas)
    mock_jip.get_stock_detail = AsyncMock(side_effect=lambda s: detail_map.get(s))

    data_as_of = _make_data_as_of()
    call_counts: list[int] = []

    for _ in range(2):
        with patch(
            "backend.agents.goldilocks_analyst.store_finding", new_callable=AsyncMock
        ) as mock_store:
            mock_store.return_value = MagicMock(id="fake-uuid")
            await run(mock_db, mock_jip, data_as_of)
            call_counts.append(mock_store.call_count)

    assert call_counts[0] == call_counts[1], (
        f"Idempotent check failed: run 1={call_counts[0]}, run 2={call_counts[1]}"
    )
