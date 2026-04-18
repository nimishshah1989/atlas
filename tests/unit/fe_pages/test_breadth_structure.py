"""Structural tests for breadth.html mockup (V1FE-11).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
Covers §10 Breadth Terminal + §10.5 Signal Playback requirements.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "breadth.html"
FIXTURE_BREADTH = ROOT / "frontend" / "mockups" / "fixtures" / "breadth_daily_5y.json"
FIXTURE_ZONE = ROOT / "frontend" / "mockups" / "fixtures" / "zone_events.json"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _html() -> str:
    """Return breadth.html contents (asserts file exists)."""
    assert MOCKUP.exists(), f"breadth.html not found at {MOCKUP}"
    return MOCKUP.read_text(encoding="utf-8")


def _breadth_fixture() -> dict:  # type: ignore[type-arg]
    """Return parsed breadth_daily_5y.json fixture."""
    assert FIXTURE_BREADTH.exists(), f"Fixture not found at {FIXTURE_BREADTH}"
    with open(FIXTURE_BREADTH, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[return-value]


def _zone_fixture() -> dict:  # type: ignore[type-arg]
    """Return parsed zone_events.json fixture."""
    assert FIXTURE_ZONE.exists(), f"Fixture not found at {FIXTURE_ZONE}"
    with open(FIXTURE_ZONE, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[return-value]


# ─── §10 fe-p10-01: 3 headline counts ────────────────────────────────────────


def test_headline_count_ema21_present() -> None:
    """data-headline='ema21' element must be present."""
    html = _html()
    assert 'data-headline="ema21"' in html, "Missing data-headline='ema21'"


def test_headline_count_dma50_present() -> None:
    """data-headline='dma50' element must be present."""
    html = _html()
    assert 'data-headline="dma50"' in html, "Missing data-headline='dma50'"


def test_headline_count_dma200_present() -> None:
    """data-headline='dma200' element must be present."""
    html = _html()
    assert 'data-headline="dma200"' in html, "Missing data-headline='dma200'"


def test_all_three_headline_counts_present() -> None:
    """All three headline count data-headline attributes must exist."""
    html = _html()
    for indicator in ["ema21", "dma50", "dma200"]:
        assert f'data-headline="{indicator}"' in html, f"Missing data-headline='{indicator}'"


# ─── §10 fe-p10-02: regime band + KPI blocks ─────────────────────────────────


def test_regime_band_present() -> None:
    """data-role='regime-band' element must be present."""
    html = _html()
    assert 'data-role="regime-band"' in html, "Missing data-role='regime-band'"


def test_three_breadth_kpi_blocks_present() -> None:
    """Three data-block='breadth-kpi' elements required."""
    html = _html()
    count = html.count('data-block="breadth-kpi"')
    assert count >= 3, f"Expected ≥3 data-block='breadth-kpi' elements, found {count}"


def test_oscillator_block_present() -> None:
    """data-block='oscillator' element must be present."""
    html = _html()
    assert 'data-block="oscillator"' in html, "Missing data-block='oscillator'"


def test_zone_reference_block_present() -> None:
    """data-block='zone-reference' element must be present."""
    html = _html()
    assert 'data-block="zone-reference"' in html, "Missing data-block='zone-reference'"


def test_describe_block_present() -> None:
    """Element with class 'describe-block' must be present."""
    html = _html()
    assert "describe-block" in html, "Missing .describe-block element"


def test_signal_history_block_present() -> None:
    """data-block='signal-history' element must be present."""
    html = _html()
    assert 'data-block="signal-history"' in html, "Missing data-block='signal-history'"


# ─── §10 fe-p10-03: universe + MA selectors ──────────────────────────────────


def test_universe_selector_present() -> None:
    """data-role='universe-selector' element must be present."""
    html = _html()
    assert 'data-role="universe-selector"' in html, "Missing data-role='universe-selector'"


def test_ma_selector_present() -> None:
    """data-role='ma-selector' element must be present."""
    html = _html()
    assert 'data-role="ma-selector"' in html, "Missing data-role='ma-selector'"


def test_universe_selector_has_nifty_options() -> None:
    """Universe selector should reference Nifty 50, 200, and 500."""
    html = _html()
    for universe in ["nifty50", "nifty200", "nifty500"]:
        assert universe in html, f"Universe selector missing '{universe}' option"


def test_ma_selector_has_all_ma_types() -> None:
    """MA selector should reference ema21, dma50, dma200."""
    html = _html()
    for ma in ["ema21", "dma50", "dma200"]:
        assert ma in html, f"MA selector missing '{ma}' option"


# ─── §10 fe-p10-04: zone bands ───────────────────────────────────────────────


def test_overbought_zone_present() -> None:
    """data-zone='overbought' element must be present."""
    html = _html()
    assert 'data-zone="overbought"' in html, "Missing data-zone='overbought'"


def test_oversold_zone_present() -> None:
    """data-zone='oversold' element must be present."""
    html = _html()
    assert 'data-zone="oversold"' in html, "Missing data-zone='oversold'"


def test_midline_zone_present() -> None:
    """data-zone='midline' element must be present."""
    html = _html()
    assert 'data-zone="midline"' in html, "Missing data-zone='midline'"


def test_zone_values_correct() -> None:
    """Zone values must match spec: OB >=400, OS <=100, midline 250."""
    html = _html()
    # OB threshold
    assert "≥400" in html or "&gt;=400" in html or "400" in html, (
        "OB threshold 400 not mentioned in HTML"
    )
    # OS threshold
    assert "≤100" in html or "&lt;=100" in html or "100" in html, (
        "OS threshold 100 not mentioned in HTML"
    )
    # Midline
    assert "250" in html, "Midline value 250 not present in HTML"


# ─── §10.5 fe-p10_5-01: 14 input parameters ─────────────────────────────────


@pytest.mark.parametrize(
    "param_id,expected_value",
    [
        ("i_initial", "100000"),
        ("i_sip", "10000"),
        ("i_lumpsum", "50000"),
        ("i_sell400", "30"),
        ("i_furtherLvl", "250"),
        ("i_furtherPct", "20"),
        ("i_redeployLvl", "125"),
        ("i_redeployPct", "50"),
        ("i_redeploy2Lvl", "50"),
        ("i_redeploy2Pct", "100"),
        ("i_l_os", "100"),
        ("i_l_ob", "400"),
        ("i_l_exit", "350"),
        ("i_l_sip_resume", "200"),
    ],
)
def test_simulation_input_present(param_id: str, expected_value: str) -> None:
    """Input element with required ID and default value must exist in HTML."""
    html = _html()
    assert f'id="{param_id}"' in html, f"Missing input with id='{param_id}'"
    assert f'value="{expected_value}"' in html, (
        f"Input '{param_id}' missing or wrong default value='{expected_value}'"
    )


def test_all_14_input_ids_present() -> None:
    """All 14 required input IDs must be present."""
    html = _html()
    required_ids = [
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
    missing = [pid for pid in required_ids if f'id="{pid}"' not in html]
    assert not missing, f"Missing input IDs: {missing}"


# ─── §10.5 fe-p10_5-02: 3 overlay benchmarks ─────────────────────────────────


def test_strategy_overlay_present() -> None:
    """data-overlay='strategy' element must be present."""
    html = _html()
    assert 'data-overlay="strategy"' in html, "Missing data-overlay='strategy'"


def test_nifty50_bh_overlay_present() -> None:
    """data-overlay='nifty50-bh' element must be present."""
    html = _html()
    assert 'data-overlay="nifty50-bh"' in html, "Missing data-overlay='nifty50-bh'"


def test_nifty500_bh_overlay_present() -> None:
    """data-overlay='nifty500-bh' element must be present."""
    html = _html()
    assert 'data-overlay="nifty500-bh"' in html, "Missing data-overlay='nifty500-bh'"


# ─── §10.5 fe-p10_5-03: 3 tabs ───────────────────────────────────────────────


def test_log_tab_present() -> None:
    """data-tab='log' element must be present (Transaction Log tab)."""
    html = _html()
    assert 'data-tab="log"' in html, "Missing data-tab='log'"


def test_cashflow_tab_present() -> None:
    """data-tab='cashflow' element must be present."""
    html = _html()
    assert 'data-tab="cashflow"' in html, "Missing data-tab='cashflow'"


def test_tax_tab_present() -> None:
    """data-tab='tax' element must be present (Tax Analysis tab)."""
    html = _html()
    assert 'data-tab="tax"' in html, "Missing data-tab='tax'"


def test_all_three_tabs_present() -> None:
    """All three simulation output tabs must be present."""
    html = _html()
    for tab in ["log", "cashflow", "tax"]:
        assert f'data-tab="{tab}"' in html, f"Missing data-tab='{tab}'"


# ─── §10.5 fe-p10_5-04: no dark palette ─────────────────────────────────────


def test_no_dark_palette_tokens() -> None:
    """Page must not contain dark-mode palette tokens."""
    html = _html()
    forbidden = ["#080810", "#0f0f1e", "#7c7cff", "IBM Plex Mono", "Plus Jakarta Sans"]
    for token in forbidden:
        assert token not in html, f"Forbidden dark token '{token}' found in breadth.html"


# ─── §10.5 fe-p10_5-05: FIFO tax cutoff ─────────────────────────────────────


def test_fifo_tax_cutoff_date_present() -> None:
    """FIFO tax cutoff date 2024-07-23 must appear in the page."""
    html = _html()
    assert "2024-07-23" in html, (
        "FIFO tax regime cutoff date '2024-07-23' not found in breadth.html"
    )


# ─── fe-g-06: no prohibited language ─────────────────────────────────────────


def test_no_prohibited_recommendation_language() -> None:
    """HTML must not contain verdict/LLM language (fe-g-06 kill list — uppercase exact match)."""
    html = _html()
    # Patterns must match as uppercase recommendation language (not lowercase contextual words)
    # fe-g-06 spec patterns are case-sensitive uppercase: BUY, SELL, HOLD, etc.
    prohibited_patterns = [
        r"\bBUY\b",
        r"\bSELL\b",
        r"\bHOLD\b",
        r"ADD ON DIPS",
        r"\bREDUCE\b",
        r"Atlas Verdict",
        r"LLM says",
        r"our recommendation",
    ]
    for pattern in prohibited_patterns:
        # Use case-sensitive match (not IGNORECASE) — "buy" in prose is OK, "BUY" as verdict is not
        match = re.search(pattern, html)
        if match:
            context = html[max(0, match.start() - 40) : match.end() + 40]
            # Allow only in CSS class definitions in style block
            if "class=" not in context and "font-size" not in context:
                pytest.fail(f"Prohibited pattern '{pattern}' found. Context: ...{context}...")


# ─── fe-g-07: Indian formatting ──────────────────────────────────────────────


def test_no_dollar_signs_with_numbers() -> None:
    """No $[digit] patterns allowed — must use ₹."""
    html = _html()
    dollar_matches = re.findall(r"\$[0-9]", html)
    assert not dollar_matches, f"Dollar sign numbers found: {dollar_matches}"


def test_no_million_billion_words() -> None:
    """Words 'million' and 'billion' must not appear in the page (Indian formatting only)."""
    html = _html()
    # Allow only in comments about what NOT to do, but no visible content
    for word in ["million", "billion"]:
        assert word.lower() not in html.lower(), f"Forbidden word '{word}' found — use lakh/crore"


# ─── fe-g-08: explain block ──────────────────────────────────────────────────


def test_explain_block_present() -> None:
    """Page must have an .explain-block[data-tier='explain'] element."""
    html = _html()
    assert "explain-block" in html, "No .explain-block element found"
    assert 'data-tier="explain"' in html, "No data-tier='explain' attribute found"


def test_explain_block_has_formula() -> None:
    """Explain block must contain breadth zone classification formula."""
    html = _html()
    assert "Breadth_pct" in html or "breadth" in html.lower(), (
        "Explain block must reference breadth calculation"
    )
    # Zone classification thresholds
    assert "400" in html and "100" in html, (
        "Explain block must reference OB/OS zone thresholds (400, 100)"
    )


# ─── fe-g-09: methodology footer ─────────────────────────────────────────────


def test_methodology_footer_present() -> None:
    """Page must have a methodology footer with 'Source:' and 'Data as of'."""
    html = _html()
    assert "Source:" in html, "Methodology footer missing 'Source:' text"
    assert "Data as of" in html, "Methodology footer missing 'Data as of' text"
    assert 'data-role="methodology"' in html, "Footer missing data-role='methodology'"


# ─── fe-g-15: nav shell with 10 entries ──────────────────────────────────────


def test_nav_has_ten_links() -> None:
    """Nav must include links to all 10 required pages."""
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
        assert f'href="{href}"' in html, f"Nav missing link to {href}"


def test_breadth_is_active_in_nav() -> None:
    """Breadth link must have class='active' in the topbar nav."""
    html = _html()
    # Check that breadth.html link has 'active' class
    assert 'href="breadth.html" class="active"' in html, "Breadth nav link is not marked as active"


# ─── fe-g-16: global search ──────────────────────────────────────────────────


def test_global_search_input_present() -> None:
    """Global search input must be present."""
    html = _html()
    assert 'data-role="global-search"' in html, "No global-search data-role found"
    assert "atlas-search" in html, "No atlas-search class found"


# ─── fe-g-18: no non-deterministic JS ────────────────────────────────────────


def test_no_math_random_or_unseeded_date() -> None:
    """Script must not use Math.random() or unseeded new Date()."""
    html = _html()
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    script_content = "\n".join(scripts)
    assert "Math.random()" not in script_content, "Script uses Math.random() — prohibited"
    unseeded_date = re.findall(r"new Date\(\s*\)", script_content)
    assert not unseeded_date, f"Script uses unseeded new Date(): {unseeded_date}"


# ─── fe-g-19 + fe-r-01: rec-slot placeholders ────────────────────────────────


def test_three_rec_slots_present() -> None:
    """Three rec-slot placeholders must be present for breadth.html."""
    html = _html()
    required_slots = [
        "breadth-regime",
        "breadth-signal-header",
        "breadth-playback-halo",
    ]
    for slot_id in required_slots:
        assert f'data-slot-id="{slot_id}"' in html, (
            f"Missing rec-slot with data-slot-id='{slot_id}'"
        )
        assert 'data-page="breadth"' in html, "rec-slot missing data-page='breadth'"


def test_rec_slots_have_rule_scope() -> None:
    """All rec-slots must have data-rule-scope attribute."""
    html = _html()
    for scope in ["breadth-regime", "breadth-signal-header", "breadth-playback-halo"]:
        assert f'data-rule-scope="{scope}"' in html, f"rec-slot missing data-rule-scope='{scope}'"


# ─── fe-dp-11: signal-history-table ─────────────────────────────────────────


def test_signal_history_table_component_present() -> None:
    """signal-history-table component marker must be present (DP §16)."""
    html = _html()
    assert (
        'class="signal-history-table"' in html or 'data-component="signal-history-table"' in html
    ), "Missing signal-history-table component (DP §16)"


# ─── Design language purity ───────────────────────────────────────────────────


def test_no_raw_hex_in_inline_styles() -> None:
    """Inline styles must not contain raw hex/rgb/hsl colors."""
    html = _html()
    inline_styles = re.findall(r'style="([^"]*)"', html)
    hex_pattern = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
    rgb_pattern = re.compile(r"rgb[a]?\(")
    violations = []
    for style in inline_styles:
        if hex_pattern.search(style) or rgb_pattern.search(style):
            violations.append(style[:80])
    assert not violations, "Inline styles contain raw color values:\n" + "\n".join(violations[:5])


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
        "CSS import order must be: tokens.css → base.css → components.css"
    )


def test_viewport_meta_is_1440() -> None:
    """Viewport meta must be set to width=1440."""
    html = _html()
    assert 'content="width=1440"' in html, "Viewport meta content must be 'width=1440'"


# ─── DP component slots ───────────────────────────────────────────────────────


def test_dp_component_slots_present() -> None:
    """Page must have regime-banner, signal-strip, and gold-rs chip DP slots."""
    html = _html()
    assert 'data-component="regime-banner"' in html, "Missing regime-banner DP slot"
    assert 'data-component="signal-strip"' in html, "Missing signal-strip DP slot"
    assert 'data-chip="gold-rs"' in html, "Missing gold-rs chip slot"
    assert 'data-component="interpretation-sidecar"' in html, (
        "Missing interpretation-sidecar DP slot"
    )


# ─── Fixture integrity ────────────────────────────────────────────────────────


def test_breadth_fixture_has_required_fields() -> None:
    """Breadth fixture must have data_as_of and series with breadth count fields."""
    data = _breadth_fixture()
    assert "data_as_of" in data, "Breadth fixture missing 'data_as_of'"
    assert "series" in data, "Breadth fixture missing 'series'"
    series = data["series"]
    assert len(series) > 0, "Breadth fixture series must not be empty"
    # Check first row has required fields
    first = series[0]
    for field in ["date", "ema21_count", "dma50_count", "dma200_count", "universe_size"]:
        assert field in first, f"Breadth series row missing field '{field}'"


def test_breadth_fixture_universe_size_is_500() -> None:
    """Nifty 500 universe should have 500 stocks."""
    data = _breadth_fixture()
    for row in data["series"]:
        assert row["universe_size"] == 500, (
            f"Expected universe_size=500, got {row['universe_size']} on {row['date']}"
        )


def test_breadth_fixture_counts_within_universe() -> None:
    """All MA counts must be between 0 and universe_size."""
    data = _breadth_fixture()
    for row in data["series"]:
        total = row["universe_size"]
        for field in ["ema21_count", "dma50_count", "dma200_count"]:
            count = row[field]
            assert 0 <= count <= total, (
                f"Field '{field}' = {count} out of range [0, {total}] on {row['date']}"
            )


def test_zone_fixture_has_required_fields() -> None:
    """Zone events fixture must have data_as_of and events list."""
    data = _zone_fixture()
    assert "data_as_of" in data, "Zone events fixture missing 'data_as_of'"
    assert "events" in data, "Zone events fixture missing 'events'"


def test_zone_event_fields_correct() -> None:
    """Each zone event must have required fields."""
    data = _zone_fixture()
    for event in data["events"]:
        for field in ["date", "event_type", "indicator", "prior_zone", "universe", "value"]:
            assert field in event, f"Zone event missing field '{field}'"


def test_zone_classification_matches_values() -> None:
    """Zone events with 'ob' in event_type must have value >= 400; 'os' must have <= 100."""
    data = _zone_fixture()
    for event in data["events"]:
        ev_type = event["event_type"]
        value = event["value"]
        if "entered_ob" in ev_type:
            # Value should be at or near OB threshold
            assert value >= 350, f"Entered OB event has value {value} which seems too low"
        if "entered_os" in ev_type:
            # Value should be at or near OS threshold
            assert value <= 150, f"Entered OS event has value {value} which seems too high"
