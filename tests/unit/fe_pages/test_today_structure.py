"""Structural tests for today.html mockup (V1FE-4).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "today.html"


# ─── Helper ──────────────────────────────────────────────────────────────────


def _html() -> str:
    """Return today.html contents (asserts file exists and is non-empty)."""
    assert MOCKUP.exists(), f"today.html not found at {MOCKUP}"
    content = MOCKUP.read_text(encoding="utf-8")
    assert len(content) > 1000, "today.html appears empty or too small"
    return content


# ─── Test 1: File exists and is non-empty ─────────────────────────────────────


def test_today_html_exists() -> None:
    """File must exist and contain substantial content."""
    html = _html()
    assert len(html) > 5000, f"today.html too small: {len(html)} chars"


# ─── Test 2: Has explain block ────────────────────────────────────────────────


def test_has_explain_block() -> None:
    """Page must contain an .explain-block or data-tier='explain' element."""
    html = _html()
    has_class = "explain-block" in html
    has_attr = 'data-tier="explain"' in html
    assert has_class or has_attr, "No .explain-block or data-tier='explain' found in today.html"


# ─── Test 3: Methodology footer with required text ────────────────────────────


def test_has_methodology_footer() -> None:
    """Methodology footer must contain 'Source:' and 'Data as of' text."""
    html = _html()
    assert "methodology-footer" in html, "No methodology-footer class found"
    assert 'data-role="methodology"' in html, "No data-role='methodology' found"
    assert "Source:" in html, "Methodology footer missing 'Source:' text"
    assert "Data as of" in html, "Methodology footer missing 'Data as of' text"


# ─── Test 4: No dollar prefix on numbers ──────────────────────────────────────


def test_no_dollar_prefix_numbers() -> None:
    """No dollar-sign-followed-by-digit should appear in HTML (fe-g-07)."""
    html = _html()
    matches = re.findall(r"\$[0-9]", html)
    assert not matches, (
        f"Found {len(matches)} occurrences of '$<digit>' pattern. "
        f"First few: {matches[:5]}. Use 'USD' prefix instead."
    )


# ─── Test 5: No kill-list words ───────────────────────────────────────────────


def test_no_kill_list_words() -> None:
    """HTML must not contain kill-list recommendation language (fe-g-06)."""
    html = _html()
    kill_patterns = [
        (r"\bHOLD\b", "HOLD"),
        (r"\bBUY\b", "BUY"),
        (r"\bSELL\b", "SELL"),
        (r"ADD ON DIPS", "ADD ON DIPS"),
        (r"\bREDUCE\b", "REDUCE"),
    ]
    for pattern, label in kill_patterns:
        match = re.search(pattern, html)
        if match:
            context = html[max(0, match.start() - 40) : match.end() + 40]
            pytest_fail_msg = (
                f"Kill-list word '{label}' found in today.html. Context: ...{context}..."
            )
            raise AssertionError(pytest_fail_msg)


# ─── Test 6: Has regime banner ────────────────────────────────────────────────


def test_has_regime_banner() -> None:
    """Page must contain data-component='regime-banner'."""
    html = _html()
    assert 'data-component="regime-banner"' in html, (
        "No data-component='regime-banner' found in today.html"
    )
    assert 'data-regime="risk-on"' in html, "regime-banner missing data-regime='risk-on' attribute"


# ─── Test 7: Has rec-slot pulse-regime ────────────────────────────────────────


def test_has_rec_slot_pulse_regime() -> None:
    """Page must contain a rec-slot with id='pulse-regime'."""
    html = _html()
    assert 'id="pulse-regime"' in html, (
        "No element with id='pulse-regime' found. rec-slot for regime missing."
    )
    assert 'class="rec-slot"' in html, "No class='rec-slot' found"
    # Must appear after the India regime banner section
    regime_pos = html.find('class="regime-banner regime-banner--correction"')
    slot_pos = html.find('id="pulse-regime"')
    assert regime_pos > 0, "India regime banner not found"
    assert slot_pos > regime_pos, "pulse-regime slot should appear after India regime banner"


# ─── Test 8: Has rec-slot pulse-sector-screen ─────────────────────────────────


def test_has_rec_slot_pulse_sector_screen() -> None:
    """Page must contain a rec-slot with id='pulse-sector-screen'."""
    html = _html()
    assert 'id="pulse-sector-screen"' in html, "No element with id='pulse-sector-screen' found"
    assert 'data-rule="rule-8"' in html, "pulse-sector-screen slot missing data-rule='rule-8'"


# ─── Test 9: Has rec-slot pulse-movers-screen ─────────────────────────────────


def test_has_rec_slot_pulse_movers_screen() -> None:
    """Page must contain a rec-slot with id='pulse-movers-screen'."""
    html = _html()
    assert 'id="pulse-movers-screen"' in html, "No element with id='pulse-movers-screen' found"
    assert 'data-rule="rule-9"' in html, "pulse-movers-screen slot missing data-rule='rule-9'"


# ─── Test 10: Has four-decision-card with data-card children ──────────────────


def test_has_four_decision_card() -> None:
    """four-decision-card must be a parent containing data-card children (fe-dp-13)."""
    html = _html()
    assert 'data-component="four-decision-card"' in html, (
        "No data-component='four-decision-card' found"
    )
    # Must have all 4 data-card variants
    for card in ["buy-side", "size-up", "size-down", "sell-side"]:
        assert f'data-card="{card}"' in html, (
            f"Missing data-card='{card}' inside four-decision-card"
        )
    # The parent must contain children (descendant selector must work)
    # Verify by checking that data-card appears AFTER data-component="four-decision-card"
    parent_pos = html.find('data-component="four-decision-card"')
    buy_pos = html.find('data-card="buy-side"')
    assert parent_pos > 0, "four-decision-card parent not found"
    assert buy_pos > parent_pos, (
        "data-card='buy-side' must appear inside four-decision-card parent, "
        "not as a sibling void element"
    )


# ─── Test 11: Has signal strip ────────────────────────────────────────────────


def test_has_signal_strip() -> None:
    """Page must contain signal strip elements."""
    html = _html()
    assert "sig-strip" in html, "No .sig-strip class found"
    assert "sig-card" in html, "No .sig-card class found"
    sig_strip_count = len(re.findall(r'class="sig-strip', html))
    assert sig_strip_count >= 2, (
        f"Expected at least 2 sig-strip blocks (global + india), found {sig_strip_count}"
    )


# ─── Test 12: Indian formatting ───────────────────────────────────────────────


def test_indian_formatting() -> None:
    """Page must use Indian formatting: ₹, Cr, lakh — not million/billion."""
    html = _html()
    assert "₹" in html, "No ₹ symbol found — financial values must use rupee symbol"
    assert "Cr" in html, "No 'Cr' (crore) found — must use Indian number formatting"
    # Must not use million/billion for financial amounts
    has_million = bool(re.search(r"\bmillion\b", html, re.IGNORECASE))
    has_billion = bool(re.search(r"\bbillion\b", html, re.IGNORECASE))
    assert not has_million, "Found 'million' — use lakh/crore instead"
    assert not has_billion, "Found 'billion' — use lakh/crore instead"


# ─── Test 13: No dark mode ────────────────────────────────────────────────────


def test_no_dark_mode() -> None:
    """Page must not include dark mode CSS or data attributes."""
    html = _html()
    assert "prefers-color-scheme: dark" not in html, (
        "Dark mode media query found — ATLAS uses white background only"
    )
    assert 'data-theme="dark"' not in html, (
        "data-theme='dark' found — ATLAS uses white background only"
    )


# ─── Test 14: Has nav links ───────────────────────────────────────────────────


def test_has_nav_links() -> None:
    """Page must have at least 10 navigation anchor elements."""
    html = _html()
    # Count all <a href= elements
    a_tags = re.findall(r"<a\s[^>]*href=", html)
    assert len(a_tags) >= 10, f"Expected at least 10 nav <a> elements, found {len(a_tags)}"
    # Must link to all required pages
    required_hrefs = [
        "today.html",
        "explore-global.html",
        "breadth.html",
        "mf-rank.html",
        "portfolios.html",
        "lab.html",
        "reports.html",
        "stock-detail.html",
    ]
    for href in required_hrefs:
        assert f'href="{href}"' in html, f"Nav missing required link to {href}"


# ─── Test 15: Responsive viewport ────────────────────────────────────────────


def test_responsive_viewport() -> None:
    """Viewport meta must use device-width for 360px no-hscroll support (fe-mob-*)."""
    html = _html()
    assert "device-width" in html, (
        "Viewport meta must contain 'device-width' for mobile responsiveness. "
        "Found width=1440 or similar fixed viewport."
    )
    # Also verify the responsive CSS was added
    assert "max-width: 639px" in html or "max-width:639px" in html, (
        "No 360px breakpoint CSS found — responsive styles must be present"
    )


# ─── Test 16: No raw hex colors in inline styles ──────────────────────────────


def test_no_raw_hex_colors_in_inline_styles() -> None:
    """Inline style attributes must not use raw hex/rgb colors — use CSS vars."""
    html = _html()
    inline_styles = re.findall(r'style="([^"]*)"', html)
    hex_pattern = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
    rgb_pattern = re.compile(r"rgb[a]?\(")
    violations = []
    for style in inline_styles:
        if hex_pattern.search(style) or rgb_pattern.search(style):
            violations.append(style[:80])
    assert not violations, (
        "Inline styles contain raw color values (use CSS vars). Violations:\n"
        + "\n".join(violations[:5])
    )
