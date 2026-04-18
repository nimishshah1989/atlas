"""
Unit tests for V1FE-2 fixture JSON files.

Tests:
1. All 8 fixture files exist
2. mf_rank_universe composite_score = round((r+k+s+c)/4, 1) for 3 sampled rows
3. sector_rrg tail length >= 8 for all sectors
4. sector_rrg quadrant values in enum
5. All fixtures have data_as_of field with date format
6. All fixtures have source field with minLength 3
7. Seed script determinism (run twice, compare output)
8. mf_rank_universe has all required fields per row
9. events categories use valid enum values
10. search_index IDs are lowercase
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = ROOT / "frontend" / "mockups" / "fixtures"

FIXTURE_FILES = [
    "events.json",
    "breadth_daily_5y.json",
    "zone_events.json",
    "search_index.json",
    "ppfas_flexi_nav_5y.json",
    "reliance_close_5y.json",
    "mf_rank_universe.json",
    "sector_rrg.json",
]

VALID_QUADRANTS = {"leading", "improving", "weakening", "lagging"}
VALID_CATEGORIES = {
    "election",
    "rbi_policy",
    "budget",
    "covid",
    "demonetisation",
    "sector_shock",
    "global_macro",
    "corporate_action",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load(filename: str) -> dict:  # type: ignore[type-arg]
    path = FIXTURES_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[return-value]


# ─── Test 1: All 8 fixture files exist ────────────────────────────────────────


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_file_exists(filename: str) -> None:
    """All 8 fixture files must exist on disk."""
    path = FIXTURES_DIR / filename
    assert path.exists(), f"Fixture file missing: {path}"
    assert path.stat().st_size > 0, f"Fixture file is empty: {path}"


# ─── Test 2: mf_rank composite_score = round((r+k+s+c)/4, 1) ─────────────────


def test_mf_rank_composite_score_formula() -> None:
    """composite_score must equal round((returns+risk+resilience+consistency)/4, 1)."""
    data = _load("mf_rank_universe.json")
    funds = data["funds"]
    assert len(funds) >= 3, "Need at least 3 funds to sample"

    # Sample 3 rows: first, middle, last
    indices = [0, len(funds) // 2, len(funds) - 1]
    for i in indices:
        fund = funds[i]
        r = fund["returns_score"]
        k = fund["risk_score"]
        s = fund["resilience_score"]
        c = fund["consistency_score"]
        expected_composite = round((r + k + s + c) / 4, 1)
        actual_composite = fund["composite_score"]
        assert actual_composite == expected_composite, (
            f"Fund {fund['fund_id']}: composite={actual_composite} "
            f"but round(({r}+{k}+{s}+{c})/4, 1)={expected_composite}"
        )


# ─── Test 3: sector_rrg tail length >= 8 per sector ──────────────────────────


def test_sector_rrg_tail_length() -> None:
    """Every sector in sector_rrg.json must have tail array with >= 8 entries."""
    data = _load("sector_rrg.json")
    sectors = data["sectors"]
    assert len(sectors) >= 1, "No sectors in sector_rrg.json"

    for sector in sectors:
        slug = sector.get("sector_slug", sector.get("sector_code", "unknown"))
        tail = sector.get("tail", [])
        assert len(tail) >= 8, f"Sector {slug!r}: tail length {len(tail)} < 8"


# ─── Test 4: sector_rrg quadrant values in enum ───────────────────────────────


def test_sector_rrg_quadrant_enum() -> None:
    """All sector quadrant values must be in the valid enum set."""
    data = _load("sector_rrg.json")
    for sector in data["sectors"]:
        quadrant = sector["quadrant"]
        assert quadrant in VALID_QUADRANTS, (
            f"Sector {sector['sector_slug']!r}: quadrant={quadrant!r} not in {VALID_QUADRANTS}"
        )


# ─── Test 5: All fixtures have data_as_of with date format ───────────────────


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_has_data_as_of(filename: str) -> None:
    """Every fixture must have data_as_of field in YYYY-MM-DD format."""
    data = _load(filename)
    assert "data_as_of" in data, f"{filename}: missing data_as_of"
    as_of = data["data_as_of"]
    assert DATE_RE.match(as_of), (
        f"{filename}: data_as_of={as_of!r} does not match YYYY-MM-DD pattern"
    )


# ─── Test 6: All fixtures have source field with length >= 3 ─────────────────


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_has_source(filename: str) -> None:
    """Every fixture must have source field with at least 3 characters."""
    data = _load(filename)
    assert "source" in data, f"{filename}: missing source field"
    source = data["source"]
    assert len(source) >= 3, f"{filename}: source={source!r} is shorter than 3 characters"


# ─── Test 7: Seed script determinism ─────────────────────────────────────────


def test_seed_script_determinism() -> None:
    """Running seed_fixtures.py twice with the same --as-of produces identical output."""
    seed_script = ROOT / "scripts" / "seed_fixtures.py"
    assert seed_script.exists(), f"seed_fixtures.py not found at {seed_script}"

    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        # Run twice with same date
        run1 = subprocess.run(
            [sys.executable, str(seed_script), "--as-of", "2026-01-15", "--output-dir", tmp1],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        assert run1.returncode == 0, f"First run failed: {run1.stderr}"

        run2 = subprocess.run(
            [sys.executable, str(seed_script), "--as-of", "2026-01-15", "--output-dir", tmp2],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        assert run2.returncode == 0, f"Second run failed: {run2.stderr}"

        # Compare all generated files
        for fname in FIXTURE_FILES:
            file1 = Path(tmp1) / fname
            file2 = Path(tmp2) / fname
            assert file1.exists(), f"File {fname} not generated in run 1"
            assert file2.exists(), f"File {fname} not generated in run 2"
            content1 = file1.read_text(encoding="utf-8")
            content2 = file2.read_text(encoding="utf-8")
            assert content1 == content2, (
                f"Non-deterministic output for {fname}: run1 != run2 "
                f"(first diff at char "
                f"{next(i for i, (a, b) in enumerate(zip(content1, content2)) if a != b)})"
            )


# ─── Test 8: mf_rank_universe has all required fields per row ────────────────


def test_mf_rank_required_fields() -> None:
    """Every fund row must have all required fields defined in the schema."""
    required_fund_fields = {
        "fund_id",
        "scheme_code",
        "scheme_name",
        "fund_name",
        "category",
        "aum_crore",
        "age_years",
        "returns_score",
        "risk_score",
        "resilience_score",
        "consistency_score",
        "composite_score",
        "rank",
        "tie_break_rank",
        "factor_inputs",
    }
    required_factor_fields = {
        "excess_return_1y",
        "excess_return_3y",
        "excess_return_5y",
        "vol_3y",
        "max_dd_3y",
        "downside_dev_3y",
        "downside_capture",
        "worst_rolling_6m",
        "rolling_12m_alpha",
        "rolling_pct_beating_bench",
    }

    data = _load("mf_rank_universe.json")
    for fund in data["funds"]:
        missing = required_fund_fields - set(fund.keys())
        assert not missing, f"Fund {fund.get('fund_id', '?')!r}: missing fields {missing}"
        fi = fund["factor_inputs"]
        missing_fi = required_factor_fields - set(fi.keys())
        assert not missing_fi, (
            f"Fund {fund.get('fund_id', '?')!r}: missing factor_inputs fields {missing_fi}"
        )


# ─── Test 9: events categories use valid enum values ─────────────────────────


def test_events_valid_categories() -> None:
    """All events must use valid category enum values."""
    data = _load("events.json")
    for event in data["events"]:
        cat = event["category"]
        assert cat in VALID_CATEGORIES, (
            f"Event {event['label']!r}: category={cat!r} not in {VALID_CATEGORIES}"
        )


# ─── Test 10: search_index IDs are lowercase ─────────────────────────────────


def test_search_index_ids_lowercase() -> None:
    """All search_index entry IDs must match ^[a-z0-9_:.-]+$ (no uppercase)."""
    id_pattern = re.compile(r"^[a-z0-9_:.-]+$")
    data = _load("search_index.json")
    for entry in data["entries"]:
        entry_id = entry["id"]
        assert id_pattern.match(entry_id), (
            f"search_index entry id={entry_id!r} contains uppercase or invalid chars"
        )
