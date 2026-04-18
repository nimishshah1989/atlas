"""Structural tests for explore-global.html mockup (V1FE-5).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "explore-global.html"


# --- Helper ------------------------------------------------------------------


def _html() -> str:
    """Return explore-global.html contents (asserts file exists and is non-empty)."""
    assert MOCKUP.exists(), f"explore-global.html not found at {MOCKUP}"
    content = MOCKUP.read_text(encoding="utf-8")
    assert len(content) > 1000, "explore-global.html appears empty or too small"
    return content


# --- Test 1: File exists and is non-empty ------------------------------------


def test_explore_global_html_exists() -> None:
    """File must exist and contain substantial content."""
    html = _html()
    assert len(html) > 5000, f"explore-global.html too small: {len(html)} chars"


# --- Test 2: Has data-block macros -------------------------------------------


def test_has_data_block_macros() -> None:
    """Page must contain data-block='macros' attribute (fe-p4-01)."""
    html = _html()
    assert 'data-block="macros"' in html, "No data-block='macros' found in explore-global.html"


# --- Test 3: Has data-block rates --------------------------------------------


def test_has_data_block_rates() -> None:
    """Page must contain data-block='rates' attribute (fe-p4-01)."""
    html = _html()
    assert 'data-block="rates"' in html, "No data-block='rates' found in explore-global.html"


# --- Test 4: Has data-block fx -----------------------------------------------


def test_has_data_block_fx() -> None:
    """Page must contain data-block='fx' attribute (fe-p4-01)."""
    html = _html()
    assert 'data-block="fx"' in html, "No data-block='fx' found in explore-global.html"


# --- Test 5: Has data-block commodities --------------------------------------


def test_has_data_block_commodities() -> None:
    """Page must contain data-block='commodities' attribute (fe-p4-01)."""
    html = _html()
    assert 'data-block="commodities"' in html, (
        "No data-block='commodities' found in explore-global.html"
    )


# --- Test 6: Has data-block credit -------------------------------------------


def test_has_data_block_credit() -> None:
    """Page must contain data-block='credit' attribute (fe-p4-01)."""
    html = _html()
    assert 'data-block="credit"' in html, "No data-block='credit' found in explore-global.html"


# --- Test 7: No dollar prefix before numbers ---------------------------------


def test_no_dollar_prefix_numbers() -> None:
    """No dollar-sign-followed-by-digit should appear in HTML (fe-g-07)."""
    html = _html()
    matches = re.findall(r"\$[0-9]", html)
    assert not matches, (
        f"Found {len(matches)} occurrences of '$<digit>' pattern. "
        f"First few: {matches[:5]}. Remove '$' prefix (use USD prefix or bare number)."
    )


# --- Test 8: No kill-list words ----------------------------------------------


def test_no_kill_list_words() -> None:
    """HTML must not contain kill-list recommendation language (fe-g-06)."""
    html = _html()
    kill_patterns = [
        (r"\bHOLD\b", "HOLD"),
        (r"\bBUY\b", "BUY"),
        (r"\bSELL\b", "SELL"),
        (r"risk-on verdict", "risk-on verdict"),
        (r"risk-off verdict", "risk-off verdict"),
    ]
    for pattern, label in kill_patterns:
        match = re.search(pattern, html)
        if match:
            context = html[max(0, match.start() - 40) : match.end() + 40]
            raise AssertionError(
                f"Kill-list word '{label}' found in explore-global.html. Context: ...{context}..."
            )


# --- Test 9: Has rec-slot global-regime --------------------------------------


def test_has_rec_slot_global_regime() -> None:
    """Page must contain a rec-slot with data-rule-scope='global-regime' (fe-g-19)."""
    html = _html()
    assert 'data-rule-scope="global-regime"' in html, (
        "No data-rule-scope='global-regime' found in explore-global.html"
    )
    assert 'class="rec-slot"' in html, "No class='rec-slot' found"
    assert 'data-slot-id="global-regime"' in html, "No data-slot-id='global-regime' found"


# --- Test 10: Has explain block ----------------------------------------------


def test_has_explain_block() -> None:
    """Page must contain an .explain-block or data-tier='explain' element."""
    html = _html()
    has_class = "explain-block" in html
    has_attr = 'data-tier="explain"' in html
    assert has_class or has_attr, (
        "No .explain-block or data-tier='explain' found in explore-global.html"
    )


# --- Test 11: Has methodology footer -----------------------------------------


def test_has_methodology_footer() -> None:
    """Methodology footer must contain 'Source:' and 'Data as of' text."""
    html = _html()
    assert "methodology-footer" in html, "No methodology-footer class found"
    assert 'data-role="methodology"' in html, "No data-role='methodology' found"
    assert "Source:" in html or "data-source=" in html, (
        "Methodology footer missing 'Source:' text or data-source attribute"
    )
    assert "Data as of" in html or "data-as-of=" in html, (
        "Methodology footer missing 'Data as of' text or data-as-of attribute"
    )
