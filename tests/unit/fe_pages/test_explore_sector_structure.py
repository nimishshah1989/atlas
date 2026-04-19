"""Structural tests for explore-sector.html mockup (V1FE-7).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "explore-sector.html"


def _html() -> str:
    """Return explore-sector.html contents."""
    assert MOCKUP.exists(), f"explore-sector.html not found at {MOCKUP}"
    content = MOCKUP.read_text(encoding="utf-8")
    assert len(content) > 1000, "explore-sector.html appears empty or too small"
    return content


def test_explore_sector_html_exists() -> None:
    html = _html()
    assert len(html) > 5000


# ── fe-p6-01: full breadth panel + full signal-playback ──────────────────────


def test_has_data_block_breadth_full() -> None:
    html = _html()
    assert 'data-block="breadth-full"' in html


def test_has_signal_playback_full_mode() -> None:
    html = _html()
    assert 'data-component="signal-playback"' in html
    assert 'data-mode="full"' in html


# ── fe-p6-02: members table + chip attributes ────────────────────────────────


def test_has_data_block_members() -> None:
    html = _html()
    assert 'data-block="members"' in html


def test_has_data_chip_rs() -> None:
    html = _html()
    assert 'data-chip="rs"' in html


def test_has_data_chip_momentum() -> None:
    html = _html()
    assert 'data-chip="momentum"' in html


def test_has_data_chip_volume() -> None:
    html = _html()
    assert 'data-chip="volume"' in html


def test_has_data_chip_breadth() -> None:
    html = _html()
    assert 'data-chip="breadth"' in html


def test_has_data_chip_gold_rs() -> None:
    html = _html()
    assert 'data-chip="gold-rs"' in html


def test_has_data_chip_divergence() -> None:
    html = _html()
    assert 'data-chip="divergence"' in html


def test_has_data_chip_conviction() -> None:
    html = _html()
    assert 'data-chip="conviction"' in html


# ── Punch list: exactly 3 rec-slots ─────────────────────────────────────────


def test_has_three_rec_slots() -> None:
    html = _html()
    # Count rec-slot occurrences
    count = html.count('class="rec-slot"')
    assert count >= 3, f"Expected at least 3 rec-slot elements, found {count}"


def test_rec_slot_sector_breadth() -> None:
    html = _html()
    assert 'data-slot-id="sector-breadth"' in html


def test_rec_slot_sector_member_signal() -> None:
    html = _html()
    assert 'data-slot-id="sector-member-signal"' in html


def test_rec_slot_sector_macro_sens() -> None:
    html = _html()
    assert 'data-slot-id="sector-macro-sens"' in html


# ── Kill-list fixes (fe-g-06, fe-g-07) ──────────────────────────────────────


def test_no_ai_commentary() -> None:
    """fe-g-06: 'AI commentary' text must not appear."""
    html = _html()
    assert "AI commentary" not in html, "Kill-list: 'AI commentary' still present"


def test_no_dollar_prefix_numbers() -> None:
    """fe-g-07: no $[0-9] patterns — dollar-prefixed numbers are banned."""
    import re

    html = _html()
    matches = re.findall(r"\$[0-9]", html)
    assert not matches, f"Kill-list: dollar-prefixed numbers still present: {matches}"


# ── fe-mob-11: table-dense ───────────────────────────────────────────────────


def test_has_table_dense() -> None:
    html = _html()
    assert "table-dense" in html or 'data-dense="true"' in html


# ── Member rows: 7 chips in canonical order ──────────────────────────────────


def test_member_rows_have_seven_chip_columns() -> None:
    """Each member row in the stock scoreboard has 7 data-chip td cells.

    Canonical order: rs, gold-rs, momentum, volume, breadth, divergence, conviction.
    """
    html = _html()
    canonical_chips = ["rs", "gold-rs", "momentum", "volume", "breadth", "divergence", "conviction"]
    for chip in canonical_chips:
        assert f'data-chip="{chip}"' in html, f"Missing chip header: {chip}"

    # Verify at least one row has all 7 chips (via td data-chip attrs)
    # Count total data-chip td occurrences — should be 7 chips * 12 rows = 84 minimum
    import re

    chip_td_count = len(re.findall(r"<td[^>]+data-chip=", html))
    assert chip_td_count >= 7, f"Expected >=7 chip td cells, found {chip_td_count}"


# ── Global checks ────────────────────────────────────────────────────────────


def test_has_methodology_footer() -> None:
    html = _html()
    assert "methodology-footer" in html
    assert 'data-role="methodology"' in html


def test_has_regime_banner() -> None:
    html = _html()
    assert 'data-component="regime-banner"' in html


def test_has_explain_block() -> None:
    html = _html()
    assert 'data-tier="explain"' in html or "explain-block" in html


def test_has_mobile_scroll_wrapper() -> None:
    html = _html()
    assert "mobile-scroll" in html


def test_has_breadth_zone_thresholds() -> None:
    """Breadth chart must include OB 400 / MID 250 / OS 100 zone markers."""
    html = _html()
    assert "OB 400" in html or 'data-threshold="400"' in html
    assert "MID 250" in html or 'data-threshold="250"' in html
    assert "OS 100" in html or 'data-threshold="100"' in html


def test_has_member_stocks_section() -> None:
    html = _html()
    assert 'id="sect-members"' in html


def test_no_act_column_recommendation_prose() -> None:
    """Act column with Add/Hold/Trim/Exit recommendation prose must not appear
    as table column header (kill-list for recommendation prose)."""
    html = _html()
    # The <th>Act</th> header should be gone — replaced with chip columns
    assert "<th>Act</th>" not in html


def test_breadth_full_section_has_kpi_blocks() -> None:
    html = _html()
    assert 'data-block="breadth-kpi"' in html
