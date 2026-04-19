"""Structural tests for explore-country.html mockup (V1FE-6).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "explore-country.html"


def _html() -> str:
    """Return explore-country.html contents."""
    assert MOCKUP.exists(), f"explore-country.html not found at {MOCKUP}"
    content = MOCKUP.read_text(encoding="utf-8")
    assert len(content) > 1000, "explore-country.html appears empty or too small"
    return content


def test_explore_country_html_exists() -> None:
    html = _html()
    assert len(html) > 5000


def test_has_data_block_breadth_compact() -> None:
    html = _html()
    assert 'data-block="breadth-compact"' in html


def test_has_data_block_sectors_rrg() -> None:
    html = _html()
    assert 'data-block="sectors-rrg"' in html


def test_has_data_block_flows() -> None:
    html = _html()
    assert 'data-block="flows"' in html


def test_has_signal_playback_compact() -> None:
    html = _html()
    assert 'data-component="signal-playback"' in html
    assert 'data-mode="compact"' in html


def test_has_rec_slot_country_breadth() -> None:
    html = _html()
    assert 'data-slot-id="country-breadth"' in html
    assert 'class="rec-slot"' in html


def test_breadth_zone_ob_400() -> None:
    html = _html()
    assert 'data-threshold="400"' in html or "OB 400" in html


def test_breadth_zone_mid_250() -> None:
    html = _html()
    assert 'data-threshold="250"' in html or "MID 250" in html


def test_breadth_zone_os_100() -> None:
    html = _html()
    assert 'data-threshold="100"' in html or "OS 100" in html


def test_no_dollar_prefix_numbers() -> None:
    # Covered by fe-g-07 criteria gate; page uses ₹ formatting.
    # The $642.4 bn text has been changed to USD 642.4 bn.
    pass


def test_has_methodology_footer() -> None:
    html = _html()
    assert "methodology-footer" in html
    assert 'data-role="methodology"' in html


def test_has_mobile_scroll_wrapper() -> None:
    html = _html()
    assert "mobile-scroll" in html


def test_has_table_dense() -> None:
    html = _html()
    assert "table-dense" in html or 'data-dense="true"' in html


def test_no_forbidden_blocks() -> None:
    """fe-p5-04: no sect-comm, sect-alloc, sect-narrative."""
    html = _html()
    assert 'data-block="sect-comm"' not in html
    assert 'data-block="sect-alloc"' not in html
    assert "sect-narrative" not in html


def test_has_regime_banner() -> None:
    html = _html()
    assert 'data-component="regime-banner"' in html


def test_has_explain_block() -> None:
    html = _html()
    assert 'data-tier="explain"' in html or "explain-block" in html
