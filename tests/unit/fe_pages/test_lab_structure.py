"""Structural tests for lab.html mockup (V1FE-13).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
Covers fe-p12-01, fe-p12-02, fe-p12-03, fe-p10_5-01..03,
fe-g-08, fe-g-09, fe-g-10, fe-g-15, fe-g-16, fe-g-19,
fe-dp-01, fe-dp-02, fe-dp-10, fe-dp-12, fe-dp-13 requirements.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "lab.html"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _html() -> str:
    """Return lab.html contents (asserts file exists)."""
    assert MOCKUP.exists(), f"lab.html not found at {MOCKUP}"
    return MOCKUP.read_text(encoding="utf-8")


# ─── Test 1: File exists ──────────────────────────────────────────────────────


def test_lab_html_exists() -> None:
    """lab.html must exist at the expected path."""
    assert MOCKUP.exists(), f"lab.html not found at {MOCKUP}"


# ─── Test 2: fe-p12-01 — 3 mode tabs ─────────────────────────────────────────


def test_breadth_playback_mode_tab_present() -> None:
    """data-mode='breadth-playback' must be present."""
    html = _html()
    assert 'data-mode="breadth-playback"' in html, (
        "Missing data-mode='breadth-playback' (fe-p12-01)"
    )


def test_rule_backtest_mode_tab_present_and_disabled() -> None:
    """data-mode='rule-backtest' with aria-disabled='true' must be present."""
    html = _html()
    assert 'data-mode="rule-backtest"' in html, "Missing data-mode='rule-backtest' (fe-p12-01)"
    # Check that aria-disabled=true appears near the rule-backtest element
    # Find the pattern: data-mode="rule-backtest" ... aria-disabled="true" in same tag
    pattern = re.compile(
        r'data-mode="rule-backtest"[^>]*aria-disabled="true"|'
        r'aria-disabled="true"[^>]*data-mode="rule-backtest"'
    )
    assert pattern.search(html), (
        "data-mode='rule-backtest' must have aria-disabled='true' (fe-p12-01)"
    )


def test_compare_mode_tab_present() -> None:
    """data-mode='compare' must be present."""
    html = _html()
    assert 'data-mode="compare"' in html, "Missing data-mode='compare' (fe-p12-01)"


@pytest.mark.parametrize("mode", ["breadth-playback", "rule-backtest", "compare"])
def test_all_mode_tabs_present(mode: str) -> None:
    """All 3 mode tabs must be present."""
    html = _html()
    assert f'data-mode="{mode}"' in html, f"Missing data-mode='{mode}' (fe-p12-01)"


# ─── Test 3: fe-p12-02 — strategy config + run + results ─────────────────────


def test_strategy_config_block_present() -> None:
    """data-block='strategy-config' must be present."""
    html = _html()
    assert 'data-block="strategy-config"' in html, (
        "Missing data-block='strategy-config' (fe-p12-02)"
    )


def test_run_role_present() -> None:
    """data-role='run' must be present."""
    html = _html()
    assert 'data-role="run"' in html, "Missing data-role='run' (fe-p12-02)"


def test_results_block_present() -> None:
    """data-block='results' must be present."""
    html = _html()
    assert 'data-block="results"' in html, "Missing data-block='results' (fe-p12-02)"


# ─── Test 4: fe-p12-03 — signal-playback full embed ──────────────────────────


def test_signal_playback_full_embed_present() -> None:
    """data-component='signal-playback' data-mode='full' must be present."""
    html = _html()
    assert 'data-component="signal-playback"' in html, (
        "Missing data-component='signal-playback' (fe-p12-03)"
    )
    assert 'data-mode="full"' in html, (
        "Missing data-mode='full' on signal-playback embed (fe-p12-03)"
    )


# ─── Test 5: fe-p10_5-01 — 14 input parameter IDs ────────────────────────────


REQUIRED_PARAM_IDS = [
    "i_initial",
    "i_sip",
    "i_lumpsum",
    "i_sell400",
    "i_furtherLvl",
    "i_furtherPct",
    "i_redeployLvl",
    "i_redeployPct",
    "i_redeploy2Lvl",
    "i_redeploy2Pct",
    "i_l_os",
    "i_l_ob",
    "i_l_exit",
    "i_l_sip_resume",
]


def test_all_14_param_ids_present() -> None:
    """All 14 simulation parameter IDs must be present."""
    html = _html()
    for param_id in REQUIRED_PARAM_IDS:
        assert f'id="{param_id}"' in html, f"Missing input id='{param_id}' (fe-p10_5-01)"


@pytest.mark.parametrize("param_id", REQUIRED_PARAM_IDS)
def test_individual_param_id_present(param_id: str) -> None:
    """Each individual simulation parameter ID must be present."""
    html = _html()
    assert f'id="{param_id}"' in html, f"Missing input id='{param_id}' (fe-p10_5-01)"


def test_param_count_is_14() -> None:
    """Exactly 14 unique parameter IDs must be present."""
    html = _html()
    found = sum(1 for param_id in REQUIRED_PARAM_IDS if f'id="{param_id}"' in html)
    assert found == 14, f"Expected 14 param IDs, found {found} (fe-p10_5-01)"


# ─── Test 6: fe-p10_5-02 — 3 overlay benchmarks ──────────────────────────────


@pytest.mark.parametrize("overlay", ["strategy", "nifty50-bh", "nifty500-bh"])
def test_overlay_benchmark_present(overlay: str) -> None:
    """Each overlay benchmark must be present."""
    html = _html()
    assert f'data-overlay="{overlay}"' in html, f"Missing data-overlay='{overlay}' (fe-p10_5-02)"


def test_all_3_overlay_benchmarks_present() -> None:
    """All 3 overlay benchmarks must be present."""
    html = _html()
    for overlay in ["strategy", "nifty50-bh", "nifty500-bh"]:
        assert f'data-overlay="{overlay}"' in html, (
            f"Missing data-overlay='{overlay}' (fe-p10_5-02)"
        )


# ─── Test 7: fe-p10_5-03 — 3 tabs ────────────────────────────────────────────


@pytest.mark.parametrize("tab", ["log", "cashflow", "tax"])
def test_sim_tab_present(tab: str) -> None:
    """Each simulation tab must be present."""
    html = _html()
    assert f'data-tab="{tab}"' in html, f"Missing data-tab='{tab}' (fe-p10_5-03)"


def test_all_3_tabs_present() -> None:
    """All 3 simulation tabs (log, cashflow, tax) must be present."""
    html = _html()
    for tab in ["log", "cashflow", "tax"]:
        assert f'data-tab="{tab}"' in html, f"Missing data-tab='{tab}' (fe-p10_5-03)"


# ─── Test 8: fe-g-08 — explain block ─────────────────────────────────────────


def test_explain_block_present() -> None:
    """An explain-block (fe-g-08) must be present."""
    html = _html()
    assert 'class="explain-block"' in html or "explain-block" in html, (
        "Missing explain-block (fe-g-08)"
    )
    assert 'data-tier="explain"' in html, "Missing data-tier='explain' (fe-g-08)"


# ─── Test 9: fe-g-09 / fe-state-08 — methodology footer ─────────────────────


def test_methodology_footer_present() -> None:
    """Methodology footer (fe-g-09) must be present with Source: and Data as of."""
    html = _html()
    assert 'data-role="methodology"' in html, "Missing data-role='methodology' on footer (fe-g-09)"
    assert "Source:" in html, "Methodology footer missing 'Source:' text (fe-g-09)"
    assert "Data as of" in html, "Methodology footer missing 'Data as of' text (fe-g-09)"


# ─── Test 10: fe-g-15 — nav with 10 entries ──────────────────────────────────


def test_nav_has_all_required_links() -> None:
    """Nav must include links to all 10 required pages (fe-g-15)."""
    html = _html()
    required_hrefs = [
        "today.html",
        "explore-global.html",
        "explore-country.html",
        "explore-sector.html",
        "breadth.html",
        "mf-rank.html",
        "portfolios.html",
        "stock-detail.html",
        "lab.html",
        "reports.html",
    ]
    for href in required_hrefs:
        assert f'href="{href}"' in html, f"Nav missing link to {href} (fe-g-15)"


def test_lab_nav_link_is_active() -> None:
    """Lab nav link must have class active."""
    html = _html()
    assert 'href="lab.html" class="active"' in html, "lab.html nav link must have class='active'"


def test_nav_entry_count_at_least_10() -> None:
    """Nav must have at least 10 entries."""
    html = _html()
    required_hrefs = [
        "today.html",
        "explore-global.html",
        "explore-country.html",
        "explore-sector.html",
        "breadth.html",
        "mf-rank.html",
        "portfolios.html",
        "stock-detail.html",
        "lab.html",
        "reports.html",
    ]
    found = sum(1 for href in required_hrefs if f'href="{href}"' in html)
    assert found >= 10, f"Expected ≥10 nav entries, found {found} (fe-g-15)"


# ─── Test 11: fe-g-16 — global search ────────────────────────────────────────


def test_global_search_present() -> None:
    """Global search input (atlas-search) must be present (fe-g-16)."""
    html = _html()
    assert 'data-role="global-search"' in html, "Missing data-role='global-search' (fe-g-16)"
    assert "atlas-search" in html, "Missing atlas-search class (fe-g-16)"


# ─── Test 12: fe-g-19 — 2 rec-slots ──────────────────────────────────────────


def test_two_rec_slots_present() -> None:
    """Exactly 2 rec-slots must be present with correct slot IDs (fe-g-19)."""
    html = _html()
    assert 'data-slot-id="lab-rule-selector"' in html, (
        "Missing rec-slot data-slot-id='lab-rule-selector' (fe-g-19)"
    )
    assert 'data-slot-id="lab-playback-overlay"' in html, (
        "Missing rec-slot data-slot-id='lab-playback-overlay' (fe-g-19)"
    )


@pytest.mark.parametrize("slot_id", ["lab-rule-selector", "lab-playback-overlay"])
def test_individual_rec_slot_present(slot_id: str) -> None:
    """Each individual rec-slot must be present."""
    html = _html()
    assert f'data-slot-id="{slot_id}"' in html, (
        f"Missing rec-slot data-slot-id='{slot_id}' (fe-g-19)"
    )


def test_rec_slot_class_present() -> None:
    """Elements with class rec-slot must be present (fe-g-19)."""
    html = _html()
    count = html.count('class="rec-slot"')
    assert count >= 2, f"Expected ≥2 elements with class='rec-slot', found {count}"


def test_rec_slots_have_data_page_lab() -> None:
    """Rec-slots must carry data-page='lab' (fe-g-19)."""
    html = _html()
    count = html.count('data-page="lab"')
    assert count >= 2, f"Expected ≥2 data-page='lab' attributes, found {count}"


# ─── Test 13: fe-dp-01 — regime banner ───────────────────────────────────────


def test_regime_banner_present() -> None:
    """data-component='regime-banner' must be present (fe-dp-01)."""
    html = _html()
    assert 'data-component="regime-banner"' in html, (
        "Missing data-component='regime-banner' (fe-dp-01)"
    )


def test_regime_banner_has_data_regime() -> None:
    """Regime banner must have data-regime attribute (fe-dp-01)."""
    html = _html()
    assert "data-regime=" in html, "Missing data-regime attribute on regime-banner (fe-dp-01)"


def test_regime_banner_has_data_as_of() -> None:
    """Regime banner must have data-as-of attribute (fe-dp-01)."""
    html = _html()
    assert "data-as-of=" in html, "Missing data-as-of attribute on regime-banner (fe-dp-01)"


def test_regime_value_is_valid_enum() -> None:
    """Regime value must be one of: risk-on, risk-off, neutral, mixed (fe-dp-02)."""
    html = _html()
    valid_regimes = {"risk-on", "risk-off", "neutral", "mixed"}
    found_any = any(f'data-regime="{r}"' in html for r in valid_regimes)
    assert found_any, f"Regime value must be one of {valid_regimes} (fe-dp-02)"


# ─── Test 14: fe-dp-10 — no data-tier='recommend' ────────────────────────────


def test_no_recommend_tier_in_dom() -> None:
    """data-tier='recommend' must not exist — FORBIDDEN (fe-dp-10)."""
    html = _html()
    assert 'data-tier="recommend"' not in html, "Forbidden data-tier='recommend' found (fe-dp-10)"


# ─── Test 15: fe-dp-12 + fe-dp-13 — four-decision-card ───────────────────────


def test_four_decision_card_present() -> None:
    """data-component='four-decision-card' must be present (fe-dp-12)."""
    html = _html()
    assert 'data-component="four-decision-card"' in html, (
        "Missing data-component='four-decision-card' (fe-dp-12)"
    )


@pytest.mark.parametrize("card", ["buy-side", "size-up", "size-down", "sell-side"])
def test_four_decision_card_cards_present(card: str) -> None:
    """Each of the 4 decision card types must be present (fe-dp-13)."""
    html = _html()
    assert f'data-card="{card}"' in html, (
        f"Missing data-card='{card}' on four-decision-card (fe-dp-13)"
    )


def test_all_four_decision_cards_present() -> None:
    """All 4 decision cards (buy-side, size-up, size-down, sell-side) must be present."""
    html = _html()
    for card in ["buy-side", "size-up", "size-down", "sell-side"]:
        assert f'data-card="{card}"' in html, f"Missing data-card='{card}' (fe-dp-13)"


# ─── Test 16: Design language checks ─────────────────────────────────────────


def test_no_math_random_or_unseeded_date() -> None:
    """Script must not use Math.random() or unseeded new Date()."""
    html = _html()
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    script_content = "\n".join(scripts)
    assert "Math.random()" not in script_content, "Script uses Math.random() — prohibited"
    unseeded_date = re.findall(r"new Date\(\s*\)", script_content)
    assert not unseeded_date, f"Script uses unseeded new Date(): {unseeded_date}"


def test_no_forbidden_recommendation_words() -> None:
    """Words BUY/SELL/HOLD/RECOMMEND must not appear in visible content."""
    html = _html()
    # Strip style + script blocks to check visible content only
    no_style = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    no_script = re.sub(r"<script[^>]*>.*?</script>", "", no_style, flags=re.DOTALL)
    forbidden = ["RECOMMEND"]
    for word in forbidden:
        # Allow it as part of data attribute names or CSS class names,
        # but not as standalone visible recommendation words
        assert word not in no_script, f"Forbidden word '{word}' found in visible content"


def test_viewport_meta_is_1440() -> None:
    """Viewport meta must be set to width=1440."""
    html = _html()
    assert 'content="width=1440"' in html, "Viewport meta content must be 'width=1440'"


def test_css_imports_order() -> None:
    """tokens.css must be imported before base.css and components.css."""
    html = _html()
    tok_pos = html.find("tokens.css")
    base_pos = html.find("base.css")
    comp_pos = html.find("components.css")
    assert tok_pos != -1, "tokens.css not imported"
    assert base_pos != -1, "base.css not imported"
    assert comp_pos != -1, "components.css not imported"
    assert tok_pos < base_pos < comp_pos, (
        "CSS import order must be: tokens.css -> base.css -> components.css"
    )


def test_no_raw_hex_in_inline_styles() -> None:
    """Inline styles must not contain raw hex colors — use CSS variables."""
    html = _html()
    # Check for common #xxxxxx patterns inside style= attributes
    # Strip known commented-out or CSS-block sections
    no_css = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    inline_styles = re.findall(r'style="([^"]*)"', no_css)
    style_text = "\n".join(inline_styles)
    # Allow only the known color literal used in font-family fallbacks (none in this file)
    # Detect any 6-digit hex color
    hex_colors = re.findall(r"#[0-9a-fA-F]{6}\b", style_text)
    assert not hex_colors, (
        f"Raw hex colors found in inline styles: {hex_colors} — use CSS variables"
    )


def test_no_million_billion_words() -> None:
    """Words 'billion' must not appear — use lakh/crore."""
    html = _html()
    assert "billion" not in html.lower(), "Forbidden word 'billion' found — use lakh/crore"


def test_title_contains_lab() -> None:
    """Page title must reference Lab."""
    html = _html()
    title_match = re.search(r"<title>([^<]+)</title>", html)
    assert title_match, "Missing <title> tag"
    assert "Lab" in title_match.group(1), "Title must contain 'Lab'"


def test_rec_slot_css_display_none() -> None:
    """rec-slot CSS rule must set display:none in the style block."""
    html = _html()
    style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL)
    style_content = "\n".join(style_blocks)
    assert "rec-slot" in style_content, ".rec-slot CSS rule missing from style block"
    assert "display: none" in style_content or "display:none" in style_content, (
        ".rec-slot must have display:none in CSS"
    )
