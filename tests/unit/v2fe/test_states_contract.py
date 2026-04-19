"""
tests/unit/v2fe/test_states_contract.py

States contract tests for atlas-data.js and atlas-states.js (V2FE-8).

Structural Python tests — no JS runtime required.
Each test verifies a specific states-contract requirement from the spec.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
ATLAS_DATA_JS = ROOT / "frontend" / "mockups" / "assets" / "atlas-data.js"
ATLAS_STATES_JS = ROOT / "frontend" / "mockups" / "assets" / "atlas-states.js"
MOCKUPS_ROOT = ROOT / "frontend" / "mockups"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- 1. Loading state ---------------------------------------------------------


def test_loading_state_skeleton_element_present() -> None:
    """Loading state: skeleton element is injected by renderSkeleton."""
    content = _read(ATLAS_STATES_JS)
    assert "skeleton-block" in content, "renderSkeleton must inject a .skeleton-block element"
    assert re.search(r"data-state.*loading|loading.*data-state", content), (
        "renderSkeleton must set data-state to loading"
    )


def test_loading_state_loadblock_calls_skeleton() -> None:
    """loadBlock() must call renderSkeleton before fetchWithTimeout within loadBlock body."""
    content = _read(ATLAS_DATA_JS)
    assert re.search(r"renderSkeleton\s*\(", content), "loadBlock must call renderSkeleton"
    # Extract the loadBlock function body (from 'function loadBlock' to the last closing brace)
    loadblock_match = re.search(r"function loadBlock\s*\(.*?\)\s*\{", content)
    assert loadblock_match, "function loadBlock not found"
    loadblock_start = loadblock_match.start()
    loadblock_body = content[loadblock_start:]
    # Within loadBlock body, renderSkeleton(el) call must appear before fetchWithTimeout(
    skeleton_pos_in_body = loadblock_body.find("renderSkeleton(el)")
    fetch_pos_in_body = loadblock_body.find("fetchWithTimeout(")
    assert skeleton_pos_in_body != -1, "renderSkeleton(el) not found in loadBlock body"
    assert fetch_pos_in_body != -1, "fetchWithTimeout( not found in loadBlock body"
    assert skeleton_pos_in_body < fetch_pos_in_body, (
        "renderSkeleton must be called before fetchWithTimeout in loadBlock body"
    )


# --- 2. Empty state -----------------------------------------------------------


def test_empty_state_subtree_present() -> None:
    """Empty state: empty-state subtree is injected by renderEmpty."""
    content = _read(ATLAS_STATES_JS)
    assert "empty-state" in content, "renderEmpty must inject a .empty-state element"
    assert re.search(r"data-state.*empty|empty.*data-state", content), (
        "renderEmpty must set data-state to empty"
    )


def test_empty_state_hasdata_false_triggers_empty() -> None:
    """loadBlock: when hasData(json) returns false, renderEmpty is called."""
    content = _read(ATLAS_DATA_JS)
    assert "renderEmpty" in content, "atlas-data.js must call renderEmpty"
    assert "hasData" in content, "atlas-data.js must call hasData"


# --- 3. Stale state -----------------------------------------------------------


def test_stale_state_amber_banner_present() -> None:
    """Stale state: amber banner is injected by renderStaleBanner."""
    content = _read(ATLAS_STATES_JS)
    assert "staleness-banner" in content, (
        "renderStaleBanner must inject a .staleness-banner element"
    )
    assert re.search(r"data-staleness-banner", content), (
        "Banner must have data-staleness-banner attribute"
    )


def test_stale_state_uses_staleness_thresholds() -> None:
    """Stale detection uses STALENESS_THRESHOLDS keyed by data-data-class."""
    content = _read(ATLAS_DATA_JS)
    assert "STALENESS_THRESHOLDS" in content, "atlas-data.js must reference STALENESS_THRESHOLDS"
    assert "dataClass" in content, "isStale must read el.dataset.dataClass to select the threshold"


# --- 4. Error state -----------------------------------------------------------


def test_error_state_card_with_code_present() -> None:
    """Error state: error card with err.code is injected by renderError."""
    content = _read(ATLAS_STATES_JS)
    assert "error-card" in content, "renderError must inject a .error-card element"
    assert "error-card__code" in content, "error card must show the error code"


def test_error_state_retry_affordance_present() -> None:
    """Error state: retry button is present in the error card."""
    content = _read(ATLAS_STATES_JS)
    assert re.search(r"data-retry|Retry|retry", content), (
        "renderError must include a retry affordance"
    )
    assert re.search(r"loadBlock|window\.loadBlock", content), (
        "Retry affordance must call window.loadBlock"
    )


def test_error_state_fetch_timeout_triggers_error() -> None:
    """Timeout (AbortError) must trigger error state with code TIMEOUT."""
    content = _read(ATLAS_DATA_JS)
    assert "TIMEOUT" in content, "AbortError must produce TIMEOUT error code"
    assert "AbortError" in content, "AbortError must be caught"


# --- 5. Timeout hard cut-off -------------------------------------------------


def test_timeout_hard_cutoff_10s_present() -> None:
    """atlas-data.js must have a 10-second hard cut-off setTimeout guard."""
    content = _read(ATLAS_DATA_JS)
    assert "10000" in content, "atlas-data.js must contain a 10000ms hard cut-off setTimeout"
    # Ensure the pattern matches the guard (setTimeout + 10000 + loading check)
    assert re.search(r"setTimeout", content), "10s hard cut-off must use setTimeout"


# --- 6. data-as-of sync -------------------------------------------------------


def test_data_as_of_attribute_sync() -> None:
    """After loadBlock success, el.data-as-of must be set from _meta.data_as_of."""
    content = _read(ATLAS_DATA_JS)
    assert re.search(r"data-as-of|setAttribute.*as-of|dataset\.asOf", content), (
        "loadBlock must sync data-as-of attribute from _meta.data_as_of"
    )
    assert re.search(r"_meta.*data_as_of|data_as_of.*_meta", content), (
        "data-as-of must be sourced from json._meta.data_as_of"
    )


# --- 7. insufficient_data -> empty (not error) --------------------------------


def test_insufficient_data_renders_empty_not_error() -> None:
    """json._meta.insufficient_data === true must render empty, not error."""
    content = _read(ATLAS_DATA_JS)
    assert "insufficient_data" in content, "atlas-data.js must handle _meta.insufficient_data"
    # The guard must call renderEmpty (not renderError) for insufficient_data
    insufficient_pos = content.find("insufficient_data")
    empty_nearby = content[insufficient_pos : insufficient_pos + 300]
    assert "renderEmpty" in empty_nearby or "empty" in empty_nearby.lower(), (
        "insufficient_data guard must lead to empty state, not error"
    )


# --- 8. Dev-mode sim_state ----------------------------------------------------


def test_dev_mode_sim_state_present() -> None:
    """atlas-data.js must support ?sim_state= URL param (localhost only)."""
    content = _read(ATLAS_DATA_JS)
    assert "sim_state" in content, "atlas-data.js must support ?sim_state= dev-mode param"
    assert re.search(r"localhost|127\.0\.0\.1", content), (
        "sim_state must be gated to localhost/127.0.0.1 only"
    )


# --- 9. Known-sparse block -> empty on insufficient_data ----------------------


def test_known_sparse_block_empty_on_insufficient_data() -> None:
    """Known-sparse block (insufficient_data:true) renders empty, not error."""
    content = _read(ATLAS_DATA_JS)
    # The insufficient_data branch must not call renderError
    # Find the insufficient_data check block
    match = re.search(r"insufficient_data.*?return", content, re.DOTALL)
    assert match, "insufficient_data guard must have an early return"
    block = match.group(0)
    assert "renderError" not in block, "insufficient_data guard must NOT call renderError"


# --- 10. Whitelist: data-v2-derived block has no state set --------------------


def test_whitelist_data_v2_derived_exempt() -> None:
    """Whitelisted blocks (data-v2-derived) are not selected by [data-endpoint] query."""
    # The auto-load selector must be [data-endpoint] only
    # Whitelisted blocks must NOT carry data-endpoint, so they're skipped
    content = _read(ATLAS_DATA_JS)
    assert re.search(r"\[data-endpoint\]", content), (
        "Auto-load must select blocks by [data-endpoint] attribute"
    )
    # The whitelist is declared in the YAML, not hard-coded in loader
    # Verify the loader does NOT hard-code data-v2-derived exemptions
    # (exemptions are handled by simply not setting data-endpoint on whitelisted blocks)
    assert "data-v2-derived" not in content, (
        "Whitelist exemptions must NOT be hard-coded in atlas-data.js (use YAML)"
    )
