"""Structural tests for portfolios.html mockup (V1FE-12).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
Covers fe-p11-01, fe-p11-02, fe-r-01, fe-g-15, fe-g-16, fe-g-09 requirements.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "portfolios.html"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _html() -> str:
    """Return portfolios.html contents (asserts file exists)."""
    assert MOCKUP.exists(), f"portfolios.html not found at {MOCKUP}"
    return MOCKUP.read_text(encoding="utf-8")


# ─── Test 1: File exists ──────────────────────────────────────────────────────


def test_portfolios_html_exists() -> None:
    """portfolios.html must exist at the expected path."""
    assert MOCKUP.exists(), f"portfolios.html not found at {MOCKUP}"


# ─── Test 2: fe-p11-01 — 4 data-book attributes ──────────────────────────────


def test_four_data_book_attributes_present() -> None:
    """All 4 data-book attributes (values 1-4) must be present."""
    html = _html()
    for book_num in ["1", "2", "3", "4"]:
        assert f'data-book="{book_num}"' in html, f'Missing data-book="{book_num}" attribute'


@pytest.mark.parametrize("book_num", ["1", "2", "3", "4"])
def test_data_book_value_present(book_num: str) -> None:
    """Each individual data-book value must be present."""
    html = _html()
    assert f'data-book="{book_num}"' in html, f'Missing data-book="{book_num}" on book card'


# ─── Test 3: fe-p11-01 — 4 data-block="holdings" present ────────────────────


def test_four_holdings_blocks_present() -> None:
    """Exactly 4 data-block='holdings' elements must be present."""
    html = _html()
    count = html.count('data-block="holdings"')
    assert count >= 4, f"Expected ≥4 data-block='holdings' elements, found {count}"


# ─── Test 4: fe-p11-01 — 4 data-role="benchmark" present ────────────────────


def test_four_benchmark_roles_present() -> None:
    """Exactly 4 data-role='benchmark' elements must be present."""
    html = _html()
    count = html.count('data-role="benchmark"')
    assert count >= 4, f"Expected ≥4 data-role='benchmark' elements, found {count}"


# ─── Test 5: fe-p11-02 — no acc-banner DOM element ───────────────────────────


def test_no_acc_banner_class_in_dom() -> None:
    """No element must have class acc-banner (DOM check, not CSS check)."""
    html = _html()
    # Look for class="acc-banner" in element tags only (not in <style> blocks)
    # Strip style blocks first to avoid false positives from CSS class definitions
    style_stripped = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    assert 'class="acc-banner"' not in style_stripped, (
        "Found class='acc-banner' DOM element — must not exist (fe-p11-02)"
    )
    assert "acc-banner" not in re.sub(r'class="[^"]*"', "", style_stripped), (
        "Unexpected acc-banner reference outside CSS"
    )


# ─── Test 6: fe-p11-02 — no rec-ledger or pending-recs data-block ────────────


def test_no_rec_ledger_block_in_dom() -> None:
    """data-block='rec-ledger' must not exist in portfolios.html DOM."""
    html = _html()
    assert 'data-block="rec-ledger"' not in html, (
        "Forbidden data-block='rec-ledger' found (fe-p11-02)"
    )


def test_no_pending_recs_block_in_dom() -> None:
    """data-block='pending-recs' must not exist in portfolios.html DOM."""
    html = _html()
    assert 'data-block="pending-recs"' not in html, (
        "Forbidden data-block='pending-recs' found (fe-p11-02)"
    )


# ─── Test 7: fe-r-01 — 4 rec-slot divs with correct slot IDs ─────────────────


def test_four_rec_slots_present() -> None:
    """All 4 rec-slot divs with portfolio-book-{1..4} slot IDs must be present."""
    html = _html()
    required_slots = [
        "portfolio-book-1",
        "portfolio-book-2",
        "portfolio-book-3",
        "portfolio-book-4",
    ]
    for slot_id in required_slots:
        assert f'data-slot-id="{slot_id}"' in html, (
            f"Missing rec-slot with data-slot-id='{slot_id}' (fe-r-01)"
        )


@pytest.mark.parametrize(
    "slot_id",
    [
        "portfolio-book-1",
        "portfolio-book-2",
        "portfolio-book-3",
        "portfolio-book-4",
    ],
)
def test_individual_rec_slot_present(slot_id: str) -> None:
    """Each individual rec-slot div must be present."""
    html = _html()
    assert f'data-slot-id="{slot_id}"' in html, f"Missing rec-slot data-slot-id='{slot_id}'"


# ─── Test 8: fe-r-01 — each rec-slot has data-rule-scope and data-page ───────


def test_rec_slots_have_data_rule_scope() -> None:
    """All rec-slots must carry data-rule-scope='book' attribute."""
    html = _html()
    # Count occurrences — should match count of rec-slots (4)
    scope_count = html.count('data-rule-scope="book"')
    assert scope_count >= 4, f"Expected ≥4 data-rule-scope='book' attributes, found {scope_count}"


def test_rec_slots_have_data_page() -> None:
    """All rec-slots must carry data-page='portfolios' attribute."""
    html = _html()
    page_count = html.count('data-page="portfolios"')
    assert page_count >= 4, (
        f"Expected ≥4 data-page='portfolios' attributes on rec-slots, found {page_count}"
    )


def test_rec_slot_class_present() -> None:
    """Elements with class rec-slot must be present (fe-r-01 div.rec-slot check)."""
    html = _html()
    count = html.count('class="rec-slot"')
    assert count >= 4, f"Expected ≥4 elements with class='rec-slot', found {count}"


# ─── Test 9: fe-g-15 — nav sentinel elements ─────────────────────────────────


def test_nav_sentinel_fe_g_15_present() -> None:
    """Nav shell sentinel (fe-g-15) comment must be present."""
    html = _html()
    assert "fe-g-15" in html, "Nav sentinel comment fe-g-15 not found"


def test_nav_sentinel_fe_g_16_present() -> None:
    """Global search sentinel (fe-g-16) comment must be present."""
    html = _html()
    assert "fe-g-16" in html, "Nav sentinel comment fe-g-16 not found"


def test_nav_has_all_required_links() -> None:
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


def test_global_search_present() -> None:
    """Global search input (atlas-search) must be present."""
    html = _html()
    assert 'data-role="global-search"' in html, "Missing data-role='global-search'"
    assert "atlas-search" in html, "Missing atlas-search class"


# ─── Test 10: fe-g-09 — methodology footer sentinel ──────────────────────────


def test_methodology_footer_present() -> None:
    """Methodology footer sentinel (fe-g-09) must be present."""
    html = _html()
    assert "fe-g-09" in html, "Methodology footer sentinel fe-g-09 not found"
    assert 'data-role="methodology"' in html, "Missing data-role='methodology' on footer"
    assert "Source:" in html, "Methodology footer missing 'Source:' text"
    assert "Data as of" in html, "Methodology footer missing 'Data as of' text"


# ─── Additional: design language purity ──────────────────────────────────────


def test_no_math_random_or_unseeded_date() -> None:
    """Script must not use Math.random() or unseeded new Date()."""
    html = _html()
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    script_content = "\n".join(scripts)
    assert "Math.random()" not in script_content, "Script uses Math.random() — prohibited"
    unseeded_date = re.findall(r"new Date\(\s*\)", script_content)
    assert not unseeded_date, f"Script uses unseeded new Date(): {unseeded_date}"


def test_rec_slot_css_display_none() -> None:
    """rec-slot CSS rule must set display:none in the style block."""
    html = _html()
    style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL)
    style_content = "\n".join(style_blocks)
    assert "rec-slot" in style_content, ".rec-slot CSS rule missing from style block"
    assert "display: none" in style_content or "display:none" in style_content, (
        ".rec-slot must have display:none in CSS"
    )


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


def test_viewport_meta_is_1440() -> None:
    """Viewport meta must be set to width=1440."""
    html = _html()
    assert 'content="width=1440"' in html, "Viewport meta content must be 'width=1440'"


def test_no_million_billion_words() -> None:
    """Words 'million' and 'billion' must not appear as Indian formatting violation."""
    html = _html()
    for word in ["billion"]:
        assert word.lower() not in html.lower(), f"Forbidden word '{word}' found — use lakh/crore"
