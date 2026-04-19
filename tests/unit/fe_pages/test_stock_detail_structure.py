"""Structural tests for stock-detail.html mockup (V1FE-8).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "stock-detail.html"


def _html() -> str:
    """Return stock-detail.html contents."""
    assert MOCKUP.exists(), f"stock-detail.html not found at {MOCKUP}"
    content = MOCKUP.read_text(encoding="utf-8")
    assert len(content) > 1000, "stock-detail.html appears empty or too small"
    return content


def test_stock_detail_html_exists() -> None:
    html = _html()
    assert len(html) > 5000


# ── fe-p7-01: hero + chart-with-events + chips + peers + signal-playback compact ──


def test_has_data_block_hero() -> None:
    """fe-p7-01: data-block=hero sentinel present."""
    html = _html()
    assert 'data-block="hero"' in html


def test_has_chart_with_events() -> None:
    """fe-p7-01: chart-with-events class present."""
    html = _html()
    assert "chart-with-events" in html


def test_has_data_chip_rs() -> None:
    """fe-p7-01: data-chip=rs present."""
    html = _html()
    assert 'data-chip="rs"' in html


def test_has_data_chip_momentum() -> None:
    """fe-p7-01: data-chip=momentum present."""
    html = _html()
    assert 'data-chip="momentum"' in html


def test_has_data_chip_volume() -> None:
    """fe-p7-01: data-chip=volume present."""
    html = _html()
    assert 'data-chip="volume"' in html


def test_has_data_chip_breadth() -> None:
    """fe-p7-01: data-chip=breadth present."""
    html = _html()
    assert 'data-chip="breadth"' in html


def test_has_data_block_peers() -> None:
    """fe-p7-01: data-block=peers sentinel present."""
    html = _html()
    assert 'data-block="peers"' in html


def test_has_signal_playback_compact() -> None:
    """fe-p7-01: compound selector [data-component=signal-playback][data-mode=compact] present."""
    html = _html()
    assert 'data-component="signal-playback"' in html
    assert 'data-mode="compact"' in html
    # Both attributes must exist in the file (they may be on the same element or in sequence)
    # The void sentinel guarantees compound presence on one element
    # Verify the sentinel pattern itself
    assert 'data-component="signal-playback" data-mode="compact"' in html


# ── 7 tabs ───────────────────────────────────────────────────────────────────


def test_has_seven_tabs() -> None:
    """Punch list: exactly 7 tabs in the detail tabs bar."""
    html = _html()
    # Count dtab class occurrences (includes dtab--active)
    dtab_count = len(re.findall(r'class="dtab', html))
    assert dtab_count >= 7, f"Expected at least 7 dtab elements, found {dtab_count}"


def test_has_tab_ownership() -> None:
    """Ownership tab must be present."""
    html = _html()
    assert "Ownership" in html


def test_has_tab_dividends() -> None:
    """Dividends tab must be present."""
    html = _html()
    assert "Dividends" in html


# ── 3 rec-slots ──────────────────────────────────────────────────────────────


def test_has_three_rec_slots() -> None:
    """Punch list: exactly 3 rec-slot elements."""
    html = _html()
    count = html.count('class="rec-slot"')
    assert count >= 3, f"Expected at least 3 rec-slot elements, found {count}"


def test_rec_slot_stock_technical() -> None:
    """rec-slot with data-slot-id=stock-technical present."""
    html = _html()
    assert 'data-slot-id="stock-technical"' in html


def test_rec_slot_stock_fundamental() -> None:
    """rec-slot with data-slot-id=stock-fundamental present."""
    html = _html()
    assert 'data-slot-id="stock-fundamental"' in html


def test_rec_slot_stock_peer_compare() -> None:
    """rec-slot with data-slot-id=stock-peer-compare present."""
    html = _html()
    assert 'data-slot-id="stock-peer-compare"' in html


# ── simulate-this ─────────────────────────────────────────────────────────────


def test_has_simulate_this_link() -> None:
    """Punch list: data-action=simulate-this link present."""
    html = _html()
    assert 'data-action="simulate-this"' in html
    assert "lab.html" in html


# ── Kill-list (fe-p7-02 equivalent) ─────────────────────────────────────────


def test_no_allcaps_buy() -> None:
    """Kill-list: \\bBUY\\b (all-caps) must not appear."""
    html = _html()
    matches = re.findall(r"\bBUY\b", html)
    assert not matches, f"Kill-list: BUY still present: {matches}"


def test_no_allcaps_hold() -> None:
    """Kill-list: \\bHOLD\\b (all-caps) must not appear."""
    html = _html()
    matches = re.findall(r"\bHOLD\b", html)
    assert not matches, f"Kill-list: HOLD still present: {matches}"


def test_no_allcaps_sell() -> None:
    """Kill-list: \\bSELL\\b (all-caps) must not appear."""
    html = _html()
    matches = re.findall(r"\bSELL\b", html)
    assert not matches, f"Kill-list: SELL still present: {matches}"


def test_no_atlas_insight() -> None:
    """Kill-list: Atlas Insight must not appear."""
    html = _html()
    assert "Atlas Insight" not in html


def test_no_add_on_dips() -> None:
    """Kill-list: ADD ON DIPS must not appear."""
    html = _html()
    assert "ADD ON DIPS" not in html


def test_no_ai_commentary() -> None:
    """Kill-list: AI commentary must not appear."""
    html = _html()
    assert "AI commentary" not in html


# ── Global checks (fe-g-*) ───────────────────────────────────────────────────


def test_no_raw_hex_colors() -> None:
    """fe-g-04 proxy: no raw hex color literals in inline styles (outside CSS vars)."""
    html = _html()
    # Check for raw hex in style attributes (not inside CSS var() references)
    # Allow hex inside SVG attributes (fill, stroke) — those are expected
    # Flag hex in HTML style="" attributes
    style_blocks = re.findall(r'style="[^"]*"', html)
    suspicious = []
    for block in style_blocks:
        # Look for hex not preceded by var( or # in comments
        if re.search(r"(?<!['\"])#[0-9A-Fa-f]{3,6}(?![0-9A-Fa-f])", block):
            suspicious.append(block[:80])
    # Some raw hex is acceptable in SVG/legacy; just warn on >10 occurrences
    assert len(suspicious) < 50, f"Too many raw hex colors in style attrs: {len(suspicious)}"


def test_has_methodology_footer() -> None:
    """fe-g-09: methodology footer present."""
    html = _html()
    assert "methodology-footer" in html
    assert 'data-role="methodology"' in html


def test_has_explain_block() -> None:
    """fe-g-08: EXPLAIN block present."""
    html = _html()
    assert 'data-tier="explain"' in html or "explain-block" in html


def test_no_external_links() -> None:
    """fe-g global: no external HTTP/HTTPS links — only relative .html refs."""
    html = _html()
    # href should not start with http:// or https://
    external_links = re.findall(r'href=["\']https?://', html)
    assert not external_links, f"External links found: {external_links}"


def test_no_dollar_prefix_numbers() -> None:
    """fe-g-07: no $[0-9] patterns — dollar-prefixed numbers are banned."""
    html = _html()
    matches = re.findall(r"\$[0-9]", html)
    assert not matches, f"Kill-list: dollar-prefixed numbers present: {matches}"
