"""Unit tests for the routine visibility endpoint (V11-0).

Tests go in tests/routes/ (NOT tests/api/) to avoid the conftest
integration-marker trap — see wiki bug-pattern conftest-integration-marker-trap.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.routines import RoutinesResponse
from backend.services.routines_service import (
    _compute_sla_breached,
    _parse_tables,
    get_routines,
)

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    """Create a mock AsyncSession that fails DB queries (graceful degradation)."""
    session = AsyncMock()
    session.execute.side_effect = Exception("DB unavailable")
    return session


def _make_db_session_with_runs(runs: list[dict[str, Any]]) -> AsyncMock:
    """Create a mock AsyncSession that returns the given run rows."""
    session = AsyncMock()

    def _build_result(rows: list[dict[str, Any]]) -> MagicMock:
        result = MagicMock()
        mappings_result = MagicMock()
        mappings_result.all.return_value = [dict(r) for r in rows]
        result.mappings.return_value = mappings_result
        return result

    # First call → DISTINCT ON query, second call → SELECT 1 check
    session.execute.side_effect = [
        _build_result(runs),
        _build_result([{"1": 1}]),  # _check_db_available
    ]
    return session


def _make_manifest_existing(
    routine_id: str = "equity_ohlcv_daily",
    sla_hours: int | None = 18,
    status: str = "live",
) -> dict[str, Any]:
    return {
        "existing": [
            {
                "id": routine_id,
                "table": f"de_{routine_id}",
                "cadence": "daily",
                "schedule": "0 19 * * 1-5",
                "source": "NSE",
                "status": status,
                "sla_freshness_hours": sla_hours,
            }
        ],
        "new_routines": [],
    }


def _make_manifest_new(routine_id: str = "india_vix_daily") -> dict[str, Any]:
    return {
        "existing": [],
        "new_routines": [
            {
                "id": routine_id,
                "priority": "P1",
                "target_table": f"de_{routine_id}",
                "cadence": "daily",
                "schedule": "30 19 * * 1-5",
                "source_url": "https://example.com",
                "history_backfill": "10y",
            }
        ],
    }


# ---------------------------------------------------------------------------
# 1. test_parse_tables_handles_comma_string
# ---------------------------------------------------------------------------


def test_parse_tables_handles_comma_string() -> None:
    result = _parse_tables("de_index_prices, de_index_technical_daily")
    assert result == ["de_index_prices", "de_index_technical_daily"]


def test_parse_tables_handles_list() -> None:
    result = _parse_tables(["de_a", "de_b"])
    assert result == ["de_a", "de_b"]


def test_parse_tables_handles_single_string() -> None:
    result = _parse_tables("de_equity_ohlcv_y{YEAR}")
    assert result == ["de_equity_ohlcv_y{YEAR}"]


def test_parse_tables_handles_none() -> None:
    result = _parse_tables(None)
    assert result == []


# ---------------------------------------------------------------------------
# 2. test_compute_sla_breached_with_none_ran_at
# ---------------------------------------------------------------------------


def test_compute_sla_breached_with_none_ran_at() -> None:
    assert _compute_sla_breached(sla_hours=18, ran_at=None) is True


def test_compute_sla_breached_no_sla() -> None:
    """If no SLA defined, never breached."""
    assert _compute_sla_breached(sla_hours=None, ran_at=None) is False


# ---------------------------------------------------------------------------
# 3. test_sla_breached_when_no_last_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sla_breached_when_no_last_run() -> None:
    """Routine with sla_hours set but no run data → sla_breached=True."""
    manifest = _make_manifest_existing(sla_hours=18)
    session = _make_session()

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert len(resp.routines) == 1
    entry = resp.routines[0]
    assert entry.sla_breached is True
    assert entry.display_status == "sla_breached"


# ---------------------------------------------------------------------------
# 4. test_sla_breached_when_run_too_old
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sla_breached_when_run_too_old() -> None:
    """Run 48h ago, SLA 18h → breach."""
    now = datetime.now(tz=UTC)
    old_ran_at = now - timedelta(hours=48)

    manifest = _make_manifest_existing(sla_hours=18)
    session = _make_db_session_with_runs(
        [
            {
                "routine_id": "equity_ohlcv_daily",
                "run_id": "abc",
                "status": "success",
                "rows_fetched": 100,
                "rows_inserted": 100,
                "rows_updated": 0,
                "duration_ms": 500,
                "error_message": None,
                "started_at": old_ran_at,
            }
        ]
    )

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert resp.routines[0].sla_breached is True


# ---------------------------------------------------------------------------
# 5. test_sla_not_breached_when_fresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sla_not_breached_when_fresh() -> None:
    """Run 1h ago, SLA 18h → no breach."""
    now = datetime.now(tz=UTC)
    fresh_ran_at = now - timedelta(hours=1)

    manifest = _make_manifest_existing(sla_hours=18)
    session = _make_db_session_with_runs(
        [
            {
                "routine_id": "equity_ohlcv_daily",
                "run_id": "abc",
                "status": "success",
                "rows_fetched": 100,
                "rows_inserted": 100,
                "rows_updated": 0,
                "duration_ms": 500,
                "error_message": None,
                "started_at": fresh_ran_at,
            }
        ]
    )

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert resp.routines[0].sla_breached is False
    assert resp.routines[0].display_status == "live"


# ---------------------------------------------------------------------------
# 6. test_new_routines_have_is_new_true
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_routines_have_is_new_true() -> None:
    manifest = _make_manifest_new()
    session = _make_session()

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert len(resp.routines) == 1
    assert resp.routines[0].is_new is True


# ---------------------------------------------------------------------------
# 7. test_existing_routines_have_is_new_false
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_routines_have_is_new_false() -> None:
    manifest = _make_manifest_existing()
    session = _make_session()

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert len(resp.routines) == 1
    assert resp.routines[0].is_new is False


# ---------------------------------------------------------------------------
# 8. test_display_status_live_when_no_breach
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_display_status_live_when_no_breach() -> None:
    now = datetime.now(tz=UTC)
    fresh = now - timedelta(hours=2)

    manifest = _make_manifest_existing(sla_hours=18)
    session = _make_db_session_with_runs(
        [
            {
                "routine_id": "equity_ohlcv_daily",
                "run_id": "r1",
                "status": "success",
                "rows_fetched": 50,
                "rows_inserted": 50,
                "rows_updated": 0,
                "duration_ms": 200,
                "error_message": None,
                "started_at": fresh,
            }
        ]
    )

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert resp.routines[0].display_status == "live"


# ---------------------------------------------------------------------------
# 9. test_display_status_sla_breached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_display_status_sla_breached() -> None:
    manifest = _make_manifest_existing(sla_hours=18)
    session = _make_session()

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert resp.routines[0].display_status == "sla_breached"


# ---------------------------------------------------------------------------
# 10. test_data_available_false_when_db_unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_data_available_false_when_db_unavailable() -> None:
    """When DB throws, data_available=False."""
    manifest = _make_manifest_existing()
    session = _make_session()

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert resp.data_available is False


# ---------------------------------------------------------------------------
# 11. test_routines_endpoint_response_shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routines_endpoint_response_shape() -> None:
    """Check RoutinesResponse shape: required fields all present."""
    manifest = {
        "existing": [
            {
                "id": "test_routine",
                "table": "de_test",
                "cadence": "daily",
                "status": "live",
            }
        ],
        "new_routines": [],
    }
    session = _make_session()

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert isinstance(resp, RoutinesResponse)
    assert isinstance(resp.total, int)
    assert isinstance(resp.live_count, int)
    assert isinstance(resp.sla_breached_count, int)
    assert isinstance(resp.data_available, bool)
    assert isinstance(resp.routines, list)


# ---------------------------------------------------------------------------
# 12. test_routines_endpoint_returns_all_manifest_routines
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routines_endpoint_returns_all_manifest_routines() -> None:
    """All routines from both existing and new_routines sections appear in response."""
    manifest = {
        "existing": [
            {"id": "r_existing_1", "table": "de_t1", "cadence": "daily", "status": "live"},
            {"id": "r_existing_2", "table": "de_t2", "cadence": "monthly", "status": "partial"},
        ],
        "new_routines": [
            {
                "id": "r_new_1",
                "priority": "P1",
                "target_table": "de_t3",
                "cadence": "daily",
                "source_url": "https://example.com",
            },
            {
                "id": "r_new_2",
                "priority": "P2",
                "target_table": "de_t4",
                "cadence": "weekly",
                "source_url": "https://example.com/2",
            },
        ],
    }
    session = _make_session()

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    assert resp.total == 4
    ids = {r.id for r in resp.routines}
    assert ids == {"r_existing_1", "r_existing_2", "r_new_1", "r_new_2"}


# ---------------------------------------------------------------------------
# 13. test_display_status_planned_for_new_routines
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_display_status_planned_for_new_routines() -> None:
    manifest = _make_manifest_new("fo_bhavcopy_daily")
    session = _make_session()

    with patch("backend.services.routines_service._load_manifest", return_value=manifest):
        resp = await get_routines(session)

    r = resp.routines[0]
    assert r.display_status == "planned"
    assert r.manifest_status == "planned"
    assert r.sla_breached is False
    assert r.priority == "P1"
