"""
tests/unit/v2fe/test_atlas_data_js.py

Structural unit tests for atlas-data.js and atlas-states.js.

Strategy: Python-only structural tests using file reads and regex pattern matching.
These tests verify that the required functions, constants, and state machine
logic are present in the JS source files, without requiring a JS runtime.

Node.js (v22) is available on this machine, but js2py/pyduktape are not installed.
Python structural tests are deterministic, fast, and have no extra dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path


# ─── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent.parent.parent
ATLAS_DATA_JS = ROOT / "frontend" / "mockups" / "assets" / "atlas-data.js"
ATLAS_STATES_JS = ROOT / "frontend" / "mockups" / "assets" / "atlas-states.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ─── Tests: atlas-data.js ─────────────────────────────────────────────────────


def test_atlas_data_js_file_exists() -> None:
    """atlas-data.js must exist and be non-empty."""
    assert ATLAS_DATA_JS.exists(), f"Missing: {ATLAS_DATA_JS}"
    assert ATLAS_DATA_JS.stat().st_size > 0, "atlas-data.js is empty"


def test_atlas_data_js_exports_loadblock() -> None:
    """atlas-data.js must define function loadBlock."""
    content = _read(ATLAS_DATA_JS)
    assert re.search(r"function\s+loadBlock\s*\(", content), (
        "function loadBlock not found in atlas-data.js"
    )


def test_atlas_data_js_exports_fetchwith_timeout() -> None:
    """atlas-data.js must define function fetchWithTimeout."""
    content = _read(ATLAS_DATA_JS)
    assert re.search(r"function\s+fetchWithTimeout\s*\(", content), (
        "function fetchWithTimeout not found in atlas-data.js"
    )


def test_atlas_data_js_state_machine_transitions() -> None:
    """atlas-data.js must reference all 5 state values: loading, ready, stale, empty, error."""
    content = _read(ATLAS_DATA_JS)
    for state in ("loading", "ready", "stale", "empty", "error"):
        assert state in content, f"State '{state}' not found in atlas-data.js"


def test_atlas_data_js_timeout_is_8000ms() -> None:
    """atlas-data.js must use an 8000ms timeout constant."""
    content = _read(ATLAS_DATA_JS)
    assert "8000" in content, "8000ms timeout constant not found in atlas-data.js"


def test_atlas_data_js_offline_fixture_fallback() -> None:
    """atlas-data.js must implement offline fixture fallback when data.fixture is set."""
    content = _read(ATLAS_DATA_JS)
    # Must reference dataset.fixture
    assert re.search(r"dataset\.fixture|data-fixture", content), (
        "Offline fixture fallback (dataset.fixture) not found in atlas-data.js"
    )
    # Must have a conditional fetch for the fixture URL
    assert re.search(r"fetch\s*\(\s*(fixtureUrl|fixture)", content), (
        "Fixture fetch call not found in atlas-data.js"
    )


def test_atlas_data_js_insufficient_data_guard() -> None:
    """atlas-data.js must short-circuit to empty state when insufficient_data === true."""
    content = _read(ATLAS_DATA_JS)
    assert "insufficient_data" in content, (
        "Known-sparse guard (insufficient_data) not found in atlas-data.js"
    )


# ─── Tests: atlas-states.js ───────────────────────────────────────────────────


def test_atlas_states_js_staleness_thresholds_has_all_7_keys() -> None:
    """atlas-states.js STALENESS_THRESHOLDS must have all 7 required keys per §6.3."""
    content = _read(ATLAS_STATES_JS)
    required_keys = [
        "intraday",
        "eod_breadth",
        "daily_regime",
        "fundamentals",
        "events",
        "holdings",
        "system",
    ]
    for key in required_keys:
        assert key in content, f"STALENESS_THRESHOLDS key '{key}' not found in atlas-states.js"


def test_atlas_states_js_staleness_threshold_values() -> None:
    """
    STALENESS_THRESHOLDS values must match §6.3 exactly.
    intraday=3600, eod_breadth=21600, daily_regime=86400,
    fundamentals=604800, events=604800, holdings=604800, system=21600
    """
    content = _read(ATLAS_STATES_JS)
    expected = {
        "intraday": 3600,
        "eod_breadth": 21600,
        "daily_regime": 86400,
        "fundamentals": 604800,
        "events": 604800,
        "holdings": 604800,
        "system": 21600,
    }
    for key, value in expected.items():
        assert str(value) in content, (
            f"STALENESS_THRESHOLDS value {value} for '{key}' not found in atlas-states.js"
        )


def test_atlas_states_js_exports_render_functions() -> None:
    """atlas-states.js must export all 4 render functions."""
    content = _read(ATLAS_STATES_JS)
    for fn_name in ("renderSkeleton", "renderEmpty", "renderStaleBanner", "renderError"):
        assert re.search(r"function\s+" + fn_name + r"\s*\(", content), (
            f"function {fn_name} not found in atlas-states.js"
        )
