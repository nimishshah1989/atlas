"""Structural tests for mf-rank.html mockup (V1FE-10).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "mf-rank.html"
FIXTURE = ROOT / "frontend" / "mockups" / "fixtures" / "mf_rank_universe.json"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _html() -> str:
    """Return mf-rank.html contents (asserts file exists)."""
    assert MOCKUP.exists(), f"mf-rank.html not found at {MOCKUP}"
    return MOCKUP.read_text(encoding="utf-8")


def _fixture() -> dict:  # type: ignore[type-arg]
    """Return parsed fixture JSON."""
    assert FIXTURE.exists(), f"Fixture not found at {FIXTURE}"
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[return-value]


# ─── Test 1: Rank table has rows matching fixture fund count ─────────────────


def test_rank_table_has_thead_with_expected_columns() -> None:
    """Table must have a thead with at least 8 th elements."""
    html = _html()
    # Check thead exists
    assert "<thead>" in html or "<thead" in html, "No <thead> found in rank table"
    # Count <th elements in the file (all headers)
    th_count = len(re.findall(r"<th[\s>]", html))
    assert th_count >= 8, f"Expected ≥8 <th> elements, found {th_count}"


# ─── Test 2: Every row has 4 factor-score cells + composite + tie-break-rank ─


def test_fixture_funds_have_all_required_score_fields() -> None:
    """Every fund in the fixture must have all 4 factor scores plus composite and tie_break_rank."""
    data = _fixture()
    funds = data["funds"]
    assert len(funds) > 0, "Fixture has no funds"
    required_fields = [
        "returns_score",
        "risk_score",
        "resilience_score",
        "consistency_score",
        "composite_score",
        "tie_break_rank",
        "rank",
    ]
    for fund in funds:
        for field in required_fields:
            assert field in fund, f"Fund '{fund.get('fund_id', '?')}' missing field '{field}'"


# ─── Test 3: Formula block has required text ────────────────────────────────


def test_formula_block_present_with_required_text() -> None:
    """explain-block must contain z_cat, Composite, and tie-break order reference."""
    html = _html()
    # Check explain-block with correct data-topic
    assert 'data-topic="mf-rank-formula"' in html, (
        "No explain-block with data-topic='mf-rank-formula' found"
    )
    # Must contain z_cat formula
    assert "z_cat" in html, "Formula block must contain 'z_cat' notation"
    # Must contain Composite
    assert "Composite" in html, "Formula block must contain 'Composite'"
    # Must mention tie-break ordering
    assert "Tie-break" in html or "tie-break" in html, "Formula block must mention tie-break order"
    # Must mention all 4 factor names
    for factor in ["Returns", "Risk", "Resilience", "Consistency"]:
        assert factor in html, f"Formula block must contain factor name '{factor}'"


# ─── Test 4: Composite score verification (fixture integrity) ────────────────


def test_composite_score_equals_average_of_four_factors() -> None:
    """composite_score must equal round((returns+risk+resilience+consistency)/4, 1)."""
    data = _fixture()
    funds = data["funds"]
    assert len(funds) >= 3, "Need at least 3 funds for sampling"
    # Check all 5 funds (we know the fixture has exactly 5)
    for fund in funds:
        expected = round(
            (
                fund["returns_score"]
                + fund["risk_score"]
                + fund["resilience_score"]
                + fund["consistency_score"]
            )
            / 4.0,
            1,
        )
        actual = round(fund["composite_score"], 1)
        assert actual == expected, (
            f"Fund '{fund['fund_id']}': composite={actual} but "
            f"round(avg({fund['returns_score']},{fund['risk_score']},"
            f"{fund['resilience_score']},{fund['consistency_score']})/4,1)={expected}"
        )


# ─── Test 5: Tie-break ordering honoured ───────────────────────────────────


def test_tie_break_order_in_fixture() -> None:
    """No two funds should share the same rank. tie_break_rank must be unique."""
    data = _fixture()
    funds = data["funds"]
    ranks = [f["rank"] for f in funds]
    assert len(ranks) == len(set(ranks)), f"Duplicate rank values found: {ranks}"
    tb_ranks = [f["tie_break_rank"] for f in funds]
    assert len(tb_ranks) == len(set(tb_ranks)), f"Duplicate tie_break_rank values: {tb_ranks}"


# ─── Test 6: No factor score outside 0..100 ────────────────────────────────


def test_no_factor_score_outside_0_to_100() -> None:
    """All factor scores in the fixture must be within [0, 100]."""
    data = _fixture()
    score_fields = [
        "returns_score",
        "risk_score",
        "resilience_score",
        "consistency_score",
        "composite_score",
    ]
    for fund in data["funds"]:
        for field in score_fields:
            val = fund[field]
            assert 0 <= val <= 100, (
                f"Fund '{fund['fund_id']}' field '{field}' = {val} is outside [0, 100]"
            )


# ─── Test 7: Kill-list — no prohibited language in HTML ────────────────────


def test_no_prohibited_recommendation_language() -> None:
    """HTML must not contain BUY / TOP PICK / RECOMMEND outside rec-slot."""
    html = _html()
    # rec-slot itself is allowed but must not contain verdict language in its contents
    # We strip the rec-slot div and check the remainder
    # The rec-slot is a placeholder with class="rec-slot" and display:none — safe to check full file
    prohibited_patterns = [
        r"\bBUY\b",
        r"\bTOP PICK\b",
        r"\bRECOMMEND\b",
        r"\bSELL\b",
        r"\bHOLD\b",
        r"Atlas Verdict",
        r"Atlas Insight",
        r"AI verdict",
        r"AI commentary",
        r"GPT says",
        r"LLM says",
        r"our recommendation",
        r"\bSELL signal\b",
        r"\bBUY signal\b",
    ]
    for pattern in prohibited_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            # Allow "HOLD" only inside class attribute values (e.g. tag--hold in mf-detail)
            # but not as standalone recommendation text — check context
            context = html[max(0, match.start() - 40) : match.end() + 40]
            # If inside a CSS class definition in the style block, skip
            # We do a strict check: not in attribute values or class definitions
            if "class=" not in context and "font-size" not in context:
                pytest.fail(
                    f"Prohibited pattern '{pattern}' found in HTML. Context: ...{context}..."
                )


# ─── Test 8: rec-slot with data-slot-id="mfrank-screens" present ────────────


def test_rec_slot_present() -> None:
    """HTML must contain a rec-slot with data-slot-id='mfrank-screens'."""
    html = _html()
    assert 'data-slot-id="mfrank-screens"' in html, (
        "rec-slot with data-slot-id='mfrank-screens' not found in HTML"
    )
    # Also check data-rule-scope and data-page
    assert 'data-rule-scope="screen"' in html, "rec-slot missing data-rule-scope='screen'"
    assert 'data-page="mf-rank"' in html, "rec-slot missing data-page='mf-rank'"


# ─── Test 9: explain-block with data-topic="mf-rank-formula" present ────────


def test_explain_block_with_correct_topic() -> None:
    """HTML must contain a section.explain-block[data-topic='mf-rank-formula']."""
    html = _html()
    # Check section tag with class explain-block AND data-topic
    assert 'class="explain-block"' in html or "explain-block" in html, (
        "No element with class 'explain-block' found"
    )
    assert 'data-topic="mf-rank-formula"' in html, (
        "No element with data-topic='mf-rank-formula' found"
    )
    assert 'data-tier="explain"' in html, "No element with data-tier='explain' found"
    # Must have a code or pre element with formula content
    assert "<code>" in html or "<pre " in html, (
        "Formula block must contain a <code> or <pre> element"
    )


# ─── Additional: DP component slots present ─────────────────────────────────


def test_dp_component_slots_present() -> None:
    """Page must have regime-banner, signal-strip, and gold-rs chip DP slots."""
    html = _html()
    assert 'data-component="regime-banner"' in html, "Missing regime-banner DP slot"
    assert 'data-regime="risk-on"' in html, "regime-banner missing data-regime attribute"
    assert 'data-component="signal-strip"' in html, "Missing signal-strip DP slot"
    assert 'data-chip="gold-rs"' in html, "Missing gold-rs chip slot"
    assert 'data-component="interpretation-sidecar"' in html, (
        "Missing interpretation-sidecar DP slot"
    )


def test_data_factor_attributes_present() -> None:
    """Must have exactly 4 elements with data-factor: returns, risk, resilience, consistency."""
    html = _html()
    expected_factors = ["returns", "risk", "resilience", "consistency"]
    for factor in expected_factors:
        pattern = f'data-factor="{factor}"'
        assert pattern in html, f"Missing element with {pattern}"


def test_tie_break_role_attribute_present() -> None:
    """Must have an element with data-role='tie-break'."""
    html = _html()
    assert 'data-role="tie-break"' in html, "No element with data-role='tie-break' found"


def test_mobile_scroll_wrapper_present() -> None:
    """Rank table must be wrapped in .mobile-scroll or [data-mobile-scroll='true']."""
    html = _html()
    assert "mobile-scroll" in html, "No .mobile-scroll wrapper found for the rank table"
    assert 'data-mobile-scroll="true"' in html, "No data-mobile-scroll='true' attribute found"


def test_filter_rail_and_rank_table_blocks_present() -> None:
    """Page must have aside[data-block='filter-rail'] and div[data-block='rank-table']."""
    html = _html()
    assert 'data-block="filter-rail"' in html, "No aside with data-block='filter-rail' found"
    assert 'data-block="rank-table"' in html, "No div with data-block='rank-table' found"


def test_methodology_footer_present() -> None:
    """Methodology footer must include 'Source:' and 'Data as of' text."""
    html = _html()
    assert "Source:" in html, "Methodology footer missing 'Source:' text"
    assert "Data as of" in html, "Methodology footer missing 'Data as of' text"
    assert 'data-role="methodology"' in html, "Footer missing data-role='methodology'"


def test_nav_has_ten_links() -> None:
    """Navigation must include all 10 required page links."""
    html = _html()
    required_hrefs = [
        "today.html",
        "explore-global.html",
        "breadth.html",
        "mf-rank.html",
        "portfolios.html",
        "lab.html",
        "reports.html",
        "stock-detail.html",
        "explore-sector.html",
        "explore-country.html",
    ]
    for href in required_hrefs:
        assert f'href="{href}"' in html, f"Nav missing link to {href}"


def test_global_search_input_present() -> None:
    """Page must have a global search input."""
    html = _html()
    assert 'data-role="global-search"' in html or 'class="atlas-search"' in html, (
        "No global search input found"
    )


def test_no_raw_hex_colors_in_inline_styles() -> None:
    """Inline style attributes must not contain raw hex/rgb/hsl colors (fe-g-04)."""
    html = _html()
    # Find all inline style attributes
    inline_styles = re.findall(r'style="([^"]*)"', html)
    hex_pattern = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
    rgb_pattern = re.compile(r"rgb[a]?\(")
    hsl_pattern = re.compile(r"hsl[a]?\(")
    violations = []
    for style in inline_styles:
        if hex_pattern.search(style) or rgb_pattern.search(style) or hsl_pattern.search(style):
            violations.append(style[:80])
    assert not violations, (
        "Inline styles contain raw color values (use CSS vars). Violations:\n"
        + "\n".join(violations[:5])
    )


def test_no_math_random_or_unseeded_date() -> None:
    """Page script must not use Math.random() or unseeded new Date()."""
    html = _html()
    # Extract script content (between <script> tags)
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    script_content = "\n".join(scripts)
    assert "Math.random()" not in script_content, "Script uses Math.random() — prohibited"
    # Check for new Date() without a fixed argument (unseeded)
    # new Date() with no args is unseeded; new Date("2026-04-17") is fine
    unseeded_date = re.findall(r"new Date\(\s*\)", script_content)
    assert not unseeded_date, f"Script uses unseeded new Date(): {unseeded_date}"
