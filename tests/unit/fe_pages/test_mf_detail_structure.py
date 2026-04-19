"""Structural tests for mf-detail.html mockup (V1FE-9).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "mf-detail.html"


def _html() -> str:
    """Return mf-detail.html contents."""
    assert MOCKUP.exists(), f"mf-detail.html not found at {MOCKUP}"
    content = MOCKUP.read_text(encoding="utf-8")
    assert len(content) > 1000, "mf-detail.html appears empty or too small"
    return content


# ── file existence ──


def test_mf_detail_html_exists() -> None:
    html = _html()
    assert len(html) > 5000


# ── fe-p8-01: data-block sentinels ──


def test_has_data_block_returns() -> None:
    html = _html()
    assert 'data-block="returns"' in html


def test_has_data_block_alpha() -> None:
    html = _html()
    assert 'data-block="alpha"' in html


def test_has_data_block_holdings() -> None:
    html = _html()
    assert 'data-block="holdings"' in html


def test_has_data_block_weighted_technicals() -> None:
    html = _html()
    assert 'data-block="weighted-technicals"' in html


def test_has_signal_playback_compact() -> None:
    """fe-p8-01: signal-playback compact mode present."""
    html = _html()
    assert 'data-component="signal-playback"' in html
    assert 'data-mode="compact"' in html


# ── fe-p8-02: kill-list tokens absent ──


def test_no_atlas_verdict_text() -> None:
    """fe-p8-02: 'Atlas Verdict' removed."""
    html = _html()
    assert "Atlas Verdict" not in html


def test_no_hold_add_on_dips() -> None:
    """fe-p8-02: 'HOLD / ADD ON DIPS' removed."""
    html = _html()
    assert "HOLD / ADD ON DIPS" not in html


def test_no_add_on_dips() -> None:
    """fe-p8-02: 'ADD ON DIPS' removed."""
    html = _html()
    assert "ADD ON DIPS" not in html


# ── rec-slots ──


def test_has_rec_slot_1() -> None:
    """2 rec-slots: first rec-slot present."""
    html = _html()
    assert 'data-slot-id="mf-alpha-thesis"' in html


def test_has_rec_slot_2() -> None:
    """2 rec-slots: second rec-slot present."""
    html = _html()
    assert 'data-slot-id="mf-risk-flag"' in html


def test_rec_slot_count_at_least_2() -> None:
    """At least 2 rec-slot elements."""
    html = _html()
    count = html.count('class="rec-slot"')
    assert count >= 2, f"Expected >=2 rec-slots, found {count}"


# ── NAV chart vs category bench TRI overlay ──


def test_nav_chart_has_benchmark_overlay() -> None:
    """NAV chart has benchmark TRI overlay (dashed line)."""
    html = _html()
    assert "Nifty MC150 TRI" in html or "MC150 TRI" in html


def test_nav_chart_has_gold_overlay() -> None:
    """NAV chart has gold overlay."""
    html = _html()
    assert "Gold" in html


# ── signal-playback lab link ──


def test_signal_playback_has_lab_link() -> None:
    """Signal playback compact has link to lab."""
    html = _html()
    assert "lab.html" in html


# ── methodology footer ──


def test_has_methodology_footer() -> None:
    """Methodology footer present."""
    html = _html()
    assert 'data-role="methodology"' in html


# ── Indian i18n ──


def test_no_dollar_amounts() -> None:
    """No $[0-9] dollar-prefixed amounts in the page."""
    html = _html()
    matches = re.findall(r"\$[0-9]", html)
    assert len(matches) == 0, f"Found dollar amounts: {matches}"


def test_uses_rupee_symbol() -> None:
    """Page uses Rs for currency."""
    html = _html()
    assert "\u20b9" in html


def test_uses_crore_not_million() -> None:
    """Uses Cr not million."""
    html = _html()
    # "Cr" should appear (e.g., "Rs71,842 Cr")
    assert " Cr" in html


# ── no dark mode ──


def test_no_dark_mode_media_query() -> None:
    """No prefers-color-scheme dark mode."""
    html = _html()
    assert "prefers-color-scheme" not in html


# ── data-as-of on methodology footer ──


def test_methodology_footer_has_data_as_of() -> None:
    html = _html()
    # The void sentinel should have data-as-of
    assert re.search(r"<footer[^>]*data-as-of=", html)
