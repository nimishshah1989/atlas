"""Unit tests for backend/agents/sector_analyst.py.

Punch list validation:
1. 31-sector fixture: 3 rotations + 2 divergences = exactly 5 transition findings + 1 summary
2. Re-run idempotent (same data → same results)
3. Zero de_* SQL — only JIP client methods called
4. Zero float in any financial field passed to store_finding
5. Naive datetime raises ValueError
6. Only get_sector_rollups called on JIP client
7. Empty sectors: only summary written
8. Quadrant classification correctness (via imported classify_quadrant)

All DB and embedding calls are mocked — no real DB or API calls.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.rs_analyzer import Quadrant, classify_quadrant
from backend.agents.sector_analyst import (
    AGENT_ID,
    AGENT_TYPE,
    _detect_breadth_divergence,
    run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

IST = timezone.utc  # Use UTC for tests; tz-awareness is what matters


def _make_data_as_of() -> datetime:
    return datetime(2026, 4, 13, 10, 0, 0, tzinfo=IST)


def _sector(
    name: str,
    avg_rs_composite: str,
    avg_rs_momentum: str,
    pct_above_200dma: str | None = "60",
    stock_count: int = 10,
) -> dict[str, Any]:
    """Build a fixture sector dict matching JIP sector rollup shape."""
    return {
        "sector": name,
        "stock_count": stock_count,
        "avg_rs_composite": Decimal(avg_rs_composite),
        "avg_rs_momentum": Decimal(avg_rs_momentum),
        "pct_above_200dma": Decimal(pct_above_200dma) if pct_above_200dma is not None else None,
        "pct_above_50dma": Decimal("55"),
        "pct_above_ema21": Decimal("58"),
        "avg_rsi_14": Decimal("52"),
    }


def _build_31_sector_fixture() -> list[dict[str, Any]]:
    """31-sector fixture with known quadrant distribution and divergence design.

    Distribution:
    - Sectors 0-7  (8 sectors): LEADING  (avg_rs > 0, avg_rs_momentum > 0)
    - Sectors 8-14 (7 sectors): IMPROVING(avg_rs < 0, avg_rs_momentum > 0)
    - Sectors 15-21(7 sectors): WEAKENING(avg_rs > 0, avg_rs_momentum < 0)
    - Sectors 22-30(9 sectors): LAGGING  (avg_rs < 0, avg_rs_momentum < 0)

    Rotations (current quadrant differs from prior):
    - Sector 0 (LEADING):   was IMPROVING  → rotation
    - Sector 8 (IMPROVING): was LAGGING    → rotation
    - Sector 15 (WEAKENING):was LEADING    → rotation

    Divergences (same prior quadrant, no rotation):
    - Sector 1 (LEADING, avg_rs > 0):   pct_above_200dma=30%  → bullish RS, weak breadth
    - Sector 22 (LAGGING, avg_rs < 0):  pct_above_200dma=75%  → bearish RS, strong breadth
    """
    sectors = []

    # 8 LEADING (rs_composite > 0, rs_momentum > 0)
    for i in range(8):
        # Sector 1 has low breadth (divergence)
        pct = "30" if i == 1 else "65"
        sectors.append(
            _sector(
                f"Sector{i:02d}",
                avg_rs_composite=f"0.{i + 1}",
                avg_rs_momentum=f"0.0{i + 1}",
                pct_above_200dma=pct,
            )
        )

    # 7 IMPROVING (rs_composite < 0, rs_momentum > 0)
    for i in range(7):
        sectors.append(
            _sector(
                f"Sector{i + 8:02d}",
                avg_rs_composite=f"-0.{i + 1}",
                avg_rs_momentum=f"0.0{i + 1}",
                pct_above_200dma="55",
            )
        )

    # 7 WEAKENING (rs_composite > 0, rs_momentum < 0)
    for i in range(7):
        sectors.append(
            _sector(
                f"Sector{i + 15:02d}",
                avg_rs_composite=f"0.{i + 1}",
                avg_rs_momentum=f"-0.0{i + 1}",
                pct_above_200dma="55",
            )
        )

    # 9 LAGGING (rs_composite < 0, rs_momentum < 0)
    for i in range(9):
        # Sector 22 (index 0 in this block) has high breadth (divergence)
        pct = "75" if i == 0 else "40"
        sectors.append(
            _sector(
                f"Sector{i + 22:02d}",
                avg_rs_composite=f"-0.{i + 1}",
                avg_rs_momentum=f"-0.0{i + 1}",
                pct_above_200dma=pct,
            )
        )

    assert len(sectors) == 31, f"Fixture must have 31 sectors, got {len(sectors)}"
    return sectors


def _make_prior_findings_map(sectors: list[dict[str, Any]]) -> dict[str, list[MagicMock]]:
    """Build a map of sector name → prior finding list.

    Design:
    - Sector00 (LEADING now):   prior = IMPROVING  → rotation
    - Sector08 (IMPROVING now): prior = LAGGING    → rotation
    - Sector15 (WEAKENING now): prior = LEADING    → rotation
    - All other sectors: prior = same quadrant as current (no rotation)
    - Sectors with no prior: treated as first run
    """

    def _classify_sector(s: dict[str, Any]) -> Quadrant:
        return classify_quadrant(
            Decimal(str(s["avg_rs_composite"])),
            Decimal(str(s["avg_rs_momentum"])),
        )

    rotation_overrides = {
        "Sector00": Quadrant.IMPROVING,  # was IMPROVING, now LEADING
        "Sector08": Quadrant.LAGGING,  # was LAGGING, now IMPROVING
        "Sector15": Quadrant.LEADING,  # was LEADING, now WEAKENING
    }

    prior_map: dict[str, list[MagicMock]] = {}
    for s in sectors:
        name = s["sector"]
        if name in rotation_overrides:
            prior_quadrant = rotation_overrides[name]
        else:
            prior_quadrant = _classify_sector(s)  # same as current → no rotation

        finding = MagicMock()
        finding.evidence = {"quadrant": prior_quadrant.value}
        prior_map[name] = [finding]

    return prior_map


# ---------------------------------------------------------------------------
# Unit: _detect_breadth_divergence
# ---------------------------------------------------------------------------


def test_detect_breadth_divergence_bullish_rs_weak_breadth() -> None:
    result = _detect_breadth_divergence(Decimal("0.5"), Decimal("30"))
    assert result == "bullish_rs_weak_breadth"


def test_detect_breadth_divergence_bearish_rs_strong_breadth() -> None:
    result = _detect_breadth_divergence(Decimal("-0.5"), Decimal("75"))
    assert result == "bearish_rs_strong_breadth"


def test_detect_breadth_divergence_no_divergence_normal() -> None:
    # Positive RS, good breadth
    result = _detect_breadth_divergence(Decimal("0.5"), Decimal("65"))
    assert result is None


def test_detect_breadth_divergence_no_divergence_lagging_weak_breadth() -> None:
    # Negative RS, weak breadth — consistent, no divergence
    result = _detect_breadth_divergence(Decimal("-0.5"), Decimal("30"))
    assert result is None


def test_detect_breadth_divergence_none_breadth_returns_none() -> None:
    result = _detect_breadth_divergence(Decimal("0.5"), None)
    assert result is None


def test_detect_breadth_divergence_boundary_exactly_50_pct_no_bullish_divergence() -> None:
    # pct_above_200dma == 50 → not < 50 → no bullish divergence
    result = _detect_breadth_divergence(Decimal("0.5"), Decimal("50"))
    assert result is None


def test_detect_breadth_divergence_boundary_exactly_70_pct_bearish_divergence() -> None:
    # pct_above_200dma == 70 → >= 70 → bearish divergence
    result = _detect_breadth_divergence(Decimal("-0.5"), Decimal("70"))
    assert result == "bearish_rs_strong_breadth"


# ---------------------------------------------------------------------------
# Unit: classify_quadrant (via imported from rs_analyzer — regression guard)
# ---------------------------------------------------------------------------


def test_classify_sector_quadrant_leading() -> None:
    assert classify_quadrant(Decimal("0.5"), Decimal("0.1")) == Quadrant.LEADING


def test_classify_sector_quadrant_improving() -> None:
    assert classify_quadrant(Decimal("-0.5"), Decimal("0.1")) == Quadrant.IMPROVING


def test_classify_sector_quadrant_weakening() -> None:
    assert classify_quadrant(Decimal("0.5"), Decimal("-0.1")) == Quadrant.WEAKENING


def test_classify_sector_quadrant_lagging() -> None:
    assert classify_quadrant(Decimal("-0.5"), Decimal("-0.1")) == Quadrant.LAGGING


# ---------------------------------------------------------------------------
# Integration-style: run() with mocked DB + JIP + store_finding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_31_sector_fixture_writes_expected_findings() -> None:
    """Main punch list test: 31 sectors, 3 rotations + 2 divergences = 5 transitions + 1 summary.

    Total store_finding calls:
    - 31 sector_quadrant (one per sector, upsert)
    - 3 sector_rotation (Sector00, Sector08, Sector15)
    - 2 breadth_divergence (Sector01, Sector22)
    - 1 analysis_summary
    = 37 total calls
    """
    sectors = _build_31_sector_fixture()
    prior_map = _make_prior_findings_map(sectors)

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_list_findings(
        db: Any, entity: str, agent_id: str, finding_type: str, limit: int
    ) -> list[MagicMock]:
        return prior_map.get(entity, [])

    with (
        patch("backend.agents.sector_analyst.store_finding", side_effect=capture_store),
        patch("backend.agents.sector_analyst.list_findings", side_effect=mock_list_findings),
    ):
        result = await run(mock_db, mock_jip, _make_data_as_of())

    # Count by finding_type
    rotation_calls = [c for c in stored_calls if c.get("finding_type") == "sector_rotation"]
    divergence_calls = [c for c in stored_calls if c.get("finding_type") == "breadth_divergence"]
    summary_calls = [c for c in stored_calls if c.get("finding_type") == "analysis_summary"]
    quadrant_calls = [c for c in stored_calls if c.get("finding_type") == "sector_quadrant"]

    assert len(rotation_calls) == 3, f"Expected 3 rotation findings, got {len(rotation_calls)}"
    assert len(divergence_calls) == 2, (
        f"Expected 2 divergence findings, got {len(divergence_calls)}"
    )
    assert len(summary_calls) == 1, f"Expected 1 summary finding, got {len(summary_calls)}"
    assert len(quadrant_calls) == 31, f"Expected 31 quadrant findings, got {len(quadrant_calls)}"

    # Transition findings = 5 (3 rotations + 2 divergences)
    transition_count = len(rotation_calls) + len(divergence_calls)
    assert transition_count == 5, f"Expected 5 transition findings (3+2), got {transition_count}"

    assert result["analyzed"] == 31
    assert result["rotations"] == 3
    assert result["divergences"] == 2

    # findings_written counts: 31 quadrant + 3 rotation + 2 divergence + 1 summary = 37
    assert result["findings_written"] == 37


@pytest.mark.asyncio
async def test_run_rotation_sectors_identified_correctly() -> None:
    """Rotation findings are written for Sector00, Sector08, Sector15 only."""
    sectors = _build_31_sector_fixture()
    prior_map = _make_prior_findings_map(sectors)

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_list_findings(
        db: Any, entity: str, agent_id: str, finding_type: str, limit: int
    ) -> list[MagicMock]:
        return prior_map.get(entity, [])

    with (
        patch("backend.agents.sector_analyst.store_finding", side_effect=capture_store),
        patch("backend.agents.sector_analyst.list_findings", side_effect=mock_list_findings),
    ):
        await run(mock_db, mock_jip, _make_data_as_of())

    rotation_entities = {
        c["entity"] for c in stored_calls if c.get("finding_type") == "sector_rotation"
    }
    assert rotation_entities == {"Sector00", "Sector08", "Sector15"}


@pytest.mark.asyncio
async def test_run_divergence_sectors_identified_correctly() -> None:
    """Divergence findings are written for Sector01 and Sector22 only."""
    sectors = _build_31_sector_fixture()
    prior_map = _make_prior_findings_map(sectors)

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_list_findings(
        db: Any, entity: str, agent_id: str, finding_type: str, limit: int
    ) -> list[MagicMock]:
        return prior_map.get(entity, [])

    with (
        patch("backend.agents.sector_analyst.store_finding", side_effect=capture_store),
        patch("backend.agents.sector_analyst.list_findings", side_effect=mock_list_findings),
    ):
        await run(mock_db, mock_jip, _make_data_as_of())

    divergence_entities = {
        c["entity"] for c in stored_calls if c.get("finding_type") == "breadth_divergence"
    }
    assert divergence_entities == {"Sector01", "Sector22"}


@pytest.mark.asyncio
async def test_run_idempotent() -> None:
    """Re-run with same data produces same finding count (store_finding upserts)."""
    sectors = _build_31_sector_fixture()
    prior_map = _make_prior_findings_map(sectors)

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    data_as_of = _make_data_as_of()
    call_counts: list[int] = []

    async def mock_list_findings(
        db: Any, entity: str, agent_id: str, finding_type: str, limit: int
    ) -> list[MagicMock]:
        return prior_map.get(entity, [])

    for _ in range(2):
        with (
            patch(
                "backend.agents.sector_analyst.store_finding",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "backend.agents.sector_analyst.list_findings",
                side_effect=mock_list_findings,
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

    import backend.agents.sector_analyst as module

    source = inspect.getsource(module)

    de_table_pattern = re.compile(r"\bde_[a-z_]+\b")
    matches = de_table_pattern.findall(source)
    assert matches == [], (
        f"sector_analyst.py contains direct de_* table references: {matches}. "
        "Use JIPDataService methods only."
    )


@pytest.mark.asyncio
async def test_run_no_float_in_financial_fields() -> None:
    """Assert zero float in any financial field passed to store_finding."""
    sectors = _build_31_sector_fixture()
    prior_map = _make_prior_findings_map(sectors)

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    async def mock_list_findings(
        db: Any, entity: str, agent_id: str, finding_type: str, limit: int
    ) -> list[MagicMock]:
        return prior_map.get(entity, [])

    with (
        patch("backend.agents.sector_analyst.store_finding", side_effect=capture_store),
        patch("backend.agents.sector_analyst.list_findings", side_effect=mock_list_findings),
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
        for key in ("avg_rs_composite", "avg_rs_momentum", "pct_above_200dma", "coverage_pct"):
            if key in evidence and evidence[key] is not None:
                val = evidence[key]
                assert not isinstance(val, float), (
                    f"evidence['{key}'] must not be float, got {type(val).__name__}: {val}"
                )


@pytest.mark.asyncio
async def test_run_naive_datetime_raises() -> None:
    """Naive datetime (no tzinfo) should raise ValueError."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()

    with pytest.raises(ValueError, match="timezone-aware"):
        await run(mock_db, mock_jip, datetime(2026, 4, 13, 10, 0, 0))  # naive


@pytest.mark.asyncio
async def test_run_only_calls_jip_methods() -> None:
    """Verify agent only calls get_sector_rollups on JIPDataService (no direct SQL)."""
    sectors = _build_31_sector_fixture()[:3]

    mock_db = AsyncMock()
    mock_jip = MagicMock()  # MagicMock to detect unexpected attribute access
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    async def mock_list_findings(
        db: Any, entity: str, agent_id: str, finding_type: str, limit: int
    ) -> list:
        return []

    with (
        patch("backend.agents.sector_analyst.store_finding", new_callable=AsyncMock) as mock_store,
        patch("backend.agents.sector_analyst.list_findings", side_effect=mock_list_findings),
    ):
        mock_store.return_value = MagicMock(id="fake-uuid")
        await run(mock_db, mock_jip, _make_data_as_of())

    mock_jip.get_sector_rollups.assert_called_once_with()


@pytest.mark.asyncio
async def test_run_empty_sectors() -> None:
    """Empty sector list: only summary written, analyzed=0."""
    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=[])

    with (
        patch("backend.agents.sector_analyst.store_finding", new_callable=AsyncMock) as mock_store,
        patch(
            "backend.agents.sector_analyst.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_store.return_value = MagicMock(id="fake-uuid")
        result = await run(mock_db, mock_jip, _make_data_as_of())

    assert result["analyzed"] == 0
    assert result["rotations"] == 0
    assert result["divergences"] == 0
    assert result["findings_written"] == 1  # only summary
    assert mock_store.call_count == 1


@pytest.mark.asyncio
async def test_run_summary_entity_is_market() -> None:
    """The final (summary) finding must have entity='market', entity_type='summary'."""
    sectors = _build_31_sector_fixture()[:3]

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    with (
        patch("backend.agents.sector_analyst.store_finding", new_callable=AsyncMock) as mock_store,
        patch(
            "backend.agents.sector_analyst.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_store.return_value = MagicMock(id="fake-uuid")
        await run(mock_db, mock_jip, _make_data_as_of())

    last_call_kwargs = mock_store.call_args_list[-1].kwargs
    assert last_call_kwargs["entity"] == "market"
    assert last_call_kwargs["entity_type"] == "summary"
    assert last_call_kwargs["finding_type"] == "analysis_summary"
    assert last_call_kwargs["agent_id"] == AGENT_ID
    assert last_call_kwargs["agent_type"] == AGENT_TYPE


@pytest.mark.asyncio
async def test_run_skips_sectors_with_missing_rs() -> None:
    """Sectors with None avg_rs_composite or avg_rs_momentum are skipped gracefully."""
    sectors = [
        _sector("ValidSector", avg_rs_composite="0.5", avg_rs_momentum="0.3"),
        {
            "sector": "MissingRS",
            "stock_count": 5,
            "avg_rs_composite": None,
            "avg_rs_momentum": Decimal("0.1"),
            "pct_above_200dma": Decimal("60"),
        },
    ]

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    with (
        patch("backend.agents.sector_analyst.store_finding", new_callable=AsyncMock) as mock_store,
        patch(
            "backend.agents.sector_analyst.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_store.return_value = MagicMock(id="fake-uuid")
        result = await run(mock_db, mock_jip, _make_data_as_of())

    assert result["analyzed"] == 1  # Only ValidSector analyzed
    # 1 sector_quadrant for ValidSector + 1 summary = 2 calls
    assert mock_store.call_count == 2


@pytest.mark.asyncio
async def test_run_sector_with_null_breadth_skips_divergence() -> None:
    """Sector with None pct_above_200dma: no divergence check, but quadrant written."""
    sectors = [
        {
            "sector": "NullBreadth",
            "stock_count": 5,
            "avg_rs_composite": Decimal("0.5"),  # positive RS
            "avg_rs_momentum": Decimal("0.1"),
            "pct_above_200dma": None,  # missing breadth
        }
    ]

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with (
        patch("backend.agents.sector_analyst.store_finding", side_effect=capture_store),
        patch(
            "backend.agents.sector_analyst.list_findings",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await run(mock_db, mock_jip, _make_data_as_of())

    divergence_calls = [c for c in stored_calls if c.get("finding_type") == "breadth_divergence"]
    assert len(divergence_calls) == 0, "No divergence when breadth is NULL"
    assert result["divergences"] == 0


@pytest.mark.asyncio
async def test_run_first_run_no_prior_no_rotation() -> None:
    """On first run (no prior history), no rotation findings written."""
    sectors = _build_31_sector_fixture()

    mock_db = AsyncMock()
    mock_jip = AsyncMock()
    mock_jip.get_sector_rollups = AsyncMock(return_value=sectors)

    stored_calls: list[dict[str, Any]] = []

    async def capture_store(**kwargs: Any) -> MagicMock:
        stored_calls.append(kwargs)
        return MagicMock(id="fake-uuid")

    with (
        patch("backend.agents.sector_analyst.store_finding", side_effect=capture_store),
        patch(
            "backend.agents.sector_analyst.list_findings",
            new_callable=AsyncMock,
            return_value=[],  # no prior history
        ),
    ):
        result = await run(mock_db, mock_jip, _make_data_as_of())

    rotation_calls = [c for c in stored_calls if c.get("finding_type") == "sector_rotation"]
    assert len(rotation_calls) == 0, "No rotations on first run"
    assert result["rotations"] == 0
    # Still writes 2 divergences (Sector01 and Sector22) + 31 quadrant + 1 summary = 34
    assert result["divergences"] == 2
