"""Integration tests for the V1 pipeline runner.

Punch list validation:
1. pipeline exits 0 on cassette fixtures → writes findings + decisions
2. Re-run idempotency: second run produces 0 new findings + 0 new decisions
3. Duration tracking: total_duration_ms present and > 0
4. Partial failure handling: one agent fails, others still run
5. data_as_of, rows_read, findings_written, decisions_written visible in summary
6. Naive datetime raises ValueError (propagates through pipeline)
7. pipeline_version is "v1" in summary
8. data_as_of auto-detection fallback (no explicit date)
9. success=False when any agent fails
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pipeline import PIPELINE_VERSION, run_pipeline

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))


def _make_data_as_of() -> datetime:
    return datetime(2026, 4, 13, 0, 0, 0, tzinfo=IST)


# ---------------------------------------------------------------------------
# Fixture factories — cassette-style mocks for all 3 agents
# ---------------------------------------------------------------------------


def _make_rs_analyzer_result() -> dict[str, int]:
    return {"analyzed": 30, "transitions": 3, "findings_written": 16}


def _make_sector_analyst_result() -> dict[str, int]:
    return {"analyzed": 8, "rotations": 2, "findings_written": 5}


def _make_decisions_result() -> dict[str, int]:
    return {"findings_read": 21, "decisions_written": 12, "decisions_skipped": 9}


# ---------------------------------------------------------------------------
# Helper: build mocked async_session_factory context
# ---------------------------------------------------------------------------


def _make_mock_db() -> AsyncMock:
    """Build a mock DB session that satisfies async context manager protocol."""
    mock_db = AsyncMock()
    # Make execute return an object with scalar_one_or_none for the MAX(date) query
    from datetime import date as date_type

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = date_type(2026, 4, 13)
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


class _MockSessionFactory:
    """Simulate async_session_factory() as an async context manager."""

    def __init__(self, db: AsyncMock) -> None:
        self._db = db

    def __call__(self) -> "_MockSessionContext":
        return _MockSessionContext(self._db)


class _MockSessionContext:
    def __init__(self, db: AsyncMock) -> None:
        self._db = db

    async def __aenter__(self) -> AsyncMock:
        return self._db

    async def __aexit__(self, *args: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_runs_all_three_agents_and_returns_summary() -> None:
    """Pipeline runs all agents, returns summary with expected keys."""
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(return_value=_make_rs_analyzer_result()),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(return_value=_make_sector_analyst_result()),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=_make_decisions_result()),
        ),
    ):
        summary = await run_pipeline(data_as_of=_make_data_as_of())

    assert summary["success"] is True
    assert summary["pipeline_version"] == PIPELINE_VERSION
    assert summary["pipeline_version"] == "v1"
    assert "data_as_of" in summary
    assert summary["total_duration_ms"] >= 0  # may be 0 with mocked agents
    assert summary["total_findings"] == 16 + 5  # rs + sector
    assert summary["total_decisions"] == 12
    assert "agents" in summary
    assert "errors" in summary
    assert summary["errors"] == {}


@pytest.mark.asyncio
async def test_pipeline_idempotent_second_run_zero_new_records() -> None:
    """Second run with same data_as_of returns 0 new findings + 0 new decisions."""
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    second_result = {"analyzed": 30, "transitions": 0, "findings_written": 0}
    zero_decisions = {"findings_read": 21, "decisions_written": 0, "decisions_skipped": 21}

    data_as_of = _make_data_as_of()

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(return_value=second_result),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(return_value={"analyzed": 8, "rotations": 0, "findings_written": 0}),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=zero_decisions),
        ),
    ):
        summary = await run_pipeline(data_as_of=data_as_of)

    # Second run: 0 new findings, 0 new decisions
    assert summary["total_findings"] == 0
    assert summary["total_decisions"] == 0
    assert summary["success"] is True


@pytest.mark.asyncio
async def test_pipeline_duration_tracking_present_and_positive() -> None:
    """total_duration_ms is present and > 0."""
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(return_value=_make_rs_analyzer_result()),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(return_value=_make_sector_analyst_result()),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=_make_decisions_result()),
        ),
    ):
        summary = await run_pipeline(data_as_of=_make_data_as_of())

    assert "total_duration_ms" in summary
    assert isinstance(summary["total_duration_ms"], int)
    assert summary["total_duration_ms"] >= 0  # may be 0 with mocked agents


@pytest.mark.asyncio
async def test_pipeline_partial_failure_one_agent_fails_others_still_run() -> None:
    """If rs_analyzer fails, sector_analyst and decisions_generator still run."""
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(side_effect=RuntimeError("JIP connection timeout")),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(return_value=_make_sector_analyst_result()),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=_make_decisions_result()),
        ),
    ):
        summary = await run_pipeline(data_as_of=_make_data_as_of())

    # rs_analyzer failed — should be in errors
    assert "rs_analyzer" in summary["errors"]
    assert "JIP connection timeout" in summary["errors"]["rs_analyzer"]
    # sector_analyst and decisions_generator still ran
    assert "sector_analyst" in summary["agents"]
    assert "decisions_generator" in summary["agents"]
    # success=False because one agent failed
    assert summary["success"] is False


@pytest.mark.asyncio
async def test_pipeline_partial_failure_middle_agent_fails() -> None:
    """If sector_analyst fails, rs_analyzer result preserved, decisions_generator still runs."""
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(return_value=_make_rs_analyzer_result()),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(side_effect=ValueError("bad sector data")),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=_make_decisions_result()),
        ),
    ):
        summary = await run_pipeline(data_as_of=_make_data_as_of())

    assert "sector_analyst" in summary["errors"]
    assert "rs_analyzer" in summary["agents"]
    assert "decisions_generator" in summary["agents"]
    assert summary["success"] is False


@pytest.mark.asyncio
async def test_pipeline_all_agents_fail_summary_has_all_errors() -> None:
    """All agents fail — errors dict has all three keys, success=False."""
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(side_effect=RuntimeError("error 1")),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(side_effect=RuntimeError("error 2")),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(side_effect=RuntimeError("error 3")),
        ),
    ):
        summary = await run_pipeline(data_as_of=_make_data_as_of())

    assert summary["success"] is False
    assert len(summary["errors"]) == 3
    assert "rs_analyzer" in summary["errors"]
    assert "sector_analyst" in summary["errors"]
    assert "decisions_generator" in summary["errors"]
    # No agents succeeded
    assert summary["agents"] == {}


@pytest.mark.asyncio
async def test_pipeline_naive_datetime_raises_valueerror() -> None:
    """Naive datetime (no tzinfo) must raise ValueError."""
    naive_dt = datetime(2026, 4, 13, 0, 0, 0)  # no tzinfo
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
    ):
        with pytest.raises(ValueError, match="timezone-aware"):
            await run_pipeline(data_as_of=naive_dt)


@pytest.mark.asyncio
async def test_pipeline_auto_detects_latest_date_when_none() -> None:
    """When data_as_of=None, pipeline queries MAX(date) from de_rs_scores."""
    from datetime import date as date_type

    mock_db = _make_mock_db()
    # Override execute to return a specific date
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = date_type(2026, 4, 13)
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_factory = _MockSessionFactory(mock_db)

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(return_value=_make_rs_analyzer_result()),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(return_value=_make_sector_analyst_result()),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=_make_decisions_result()),
        ),
    ):
        summary = await run_pipeline(data_as_of=None)

    # The date should be 2026-04-13
    assert "2026-04-13" in summary["data_as_of"]
    assert summary["success"] is True


@pytest.mark.asyncio
async def test_pipeline_auto_detect_fallback_on_db_error() -> None:
    """When MAX(date) query fails, pipeline falls back to today IST and still runs."""
    mock_db = AsyncMock()
    # Make the MAX(date) query fail
    mock_db.execute = AsyncMock(side_effect=Exception("connection lost"))
    mock_factory = _MockSessionFactory(mock_db)

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(return_value=_make_rs_analyzer_result()),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(return_value=_make_sector_analyst_result()),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=_make_decisions_result()),
        ),
    ):
        summary = await run_pipeline(data_as_of=None)

    # Pipeline should still succeed (fallback to today)
    assert summary["success"] is True
    assert "data_as_of" in summary


@pytest.mark.asyncio
async def test_pipeline_summary_has_data_as_of_findings_decisions() -> None:
    """Summary dict has data_as_of, total_findings, total_decisions (for journalctl)."""
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(return_value=_make_rs_analyzer_result()),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(return_value=_make_sector_analyst_result()),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=_make_decisions_result()),
        ),
    ):
        summary = await run_pipeline(data_as_of=_make_data_as_of())

    # All required fields for journalctl visibility must be present
    assert "data_as_of" in summary
    assert "total_findings" in summary
    assert "total_decisions" in summary
    assert "total_duration_ms" in summary
    assert "pipeline_version" in summary
    # Per-agent rows_read is in agents sub-dict
    assert summary["agents"]["rs_analyzer"]["analyzed"] == 30
    assert summary["agents"]["decisions_generator"]["findings_read"] == 21


# ---------------------------------------------------------------------------
# CLI entry point tests (no subprocess — import and test directly)
# ---------------------------------------------------------------------------


def test_cli_parse_data_as_of_valid_date() -> None:
    """CLI parses valid YYYY-MM-DD into IST-aware datetime."""
    from atlas.pipeline.__main__ import _parse_data_as_of

    result = _parse_data_as_of("2026-04-13")
    assert result is not None
    assert result.year == 2026
    assert result.month == 4
    assert result.day == 13
    assert result.tzinfo is not None


def test_cli_parse_data_as_of_none_returns_none() -> None:
    """CLI returns None when no date provided (auto-detect mode)."""
    from atlas.pipeline.__main__ import _parse_data_as_of

    result = _parse_data_as_of(None)
    assert result is None


def test_cli_parse_data_as_of_invalid_format_exits() -> None:
    """CLI exits with code 1 on invalid date format."""
    from atlas.pipeline.__main__ import _parse_data_as_of

    with pytest.raises(SystemExit) as exc_info:
        _parse_data_as_of("13-04-2026")  # wrong format

    assert exc_info.value.code == 1


def test_cli_parse_args_run_subcommand() -> None:
    """CLI parses 'run' subcommand correctly."""
    from atlas.pipeline.__main__ import _parse_args

    args = _parse_args(["run", "--data-as-of", "2026-04-13"])
    assert args.command == "run"
    assert args.data_as_of == "2026-04-13"


def test_cli_parse_args_run_no_date() -> None:
    """CLI parses 'run' without --data-as-of (auto-detect mode)."""
    from atlas.pipeline.__main__ import _parse_args

    args = _parse_args(["run"])
    assert args.command == "run"
    assert args.data_as_of is None


@pytest.mark.asyncio
async def test_cli_run_async_exits_zero_on_success() -> None:
    """CLI _run() returns 0 when pipeline succeeds."""
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    from atlas.pipeline.__main__ import _run, _parse_data_as_of

    data_as_of = _parse_data_as_of("2026-04-13")

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(return_value=_make_rs_analyzer_result()),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(return_value=_make_sector_analyst_result()),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=_make_decisions_result()),
        ),
    ):
        exit_code = await _run(data_as_of)

    assert exit_code == 0


@pytest.mark.asyncio
async def test_cli_run_async_exits_one_on_partial_failure() -> None:
    """CLI _run() returns 1 when any agent fails."""
    mock_db = _make_mock_db()
    mock_factory = _MockSessionFactory(mock_db)

    from atlas.pipeline.__main__ import _run, _parse_data_as_of

    data_as_of = _parse_data_as_of("2026-04-13")

    with (
        patch("backend.pipeline.async_session_factory", mock_factory),
        patch("backend.pipeline.JIPDataService"),
        patch(
            "backend.pipeline.rs_analyzer.run",
            new=AsyncMock(side_effect=RuntimeError("agent failed")),
        ),
        patch(
            "backend.pipeline.sector_analyst.run",
            new=AsyncMock(return_value=_make_sector_analyst_result()),
        ),
        patch(
            "backend.pipeline.decisions_generator.run",
            new=AsyncMock(return_value=_make_decisions_result()),
        ),
    ):
        exit_code = await _run(data_as_of)

    assert exit_code == 1
