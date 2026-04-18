"""Structural tests for index.html mockup (V1FE-3).

Tests verify static HTML structure via regex/string matching only.
No external DOM libraries (no beautifulsoup).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCKUP = ROOT / "frontend" / "mockups" / "index.html"

# The 10 Stage-1 pages that index.html must link to.
REQUIRED_HREFS = [
    "today.html",
    "explore-global.html",
    "explore-country.html",
    "explore-sector.html",
    "stock-detail.html",
    "mf-detail.html",
    "mf-rank.html",
    "breadth.html",
    "portfolios.html",
    "lab.html",
]


# ─── Helper ──────────────────────────────────────────────────────────────────


def _html() -> str:
    """Return index.html contents (asserts file exists and is non-empty)."""
    assert MOCKUP.exists(), f"index.html not found at {MOCKUP}"
    content = MOCKUP.read_text(encoding="utf-8")
    assert len(content) > 0, "index.html is empty"
    return content


# ─── Test 1: File exists and has valid HTML structure ────────────────────────


def test_index_file_exists_with_valid_html_structure() -> None:
    """index.html must exist, be non-empty, and have DOCTYPE + lang + meta charset."""
    html = _html()
    assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower(), (
        "index.html missing <!DOCTYPE html>"
    )
    assert 'lang="en"' in html, "index.html missing lang='en' attribute on <html>"
    assert 'charset="UTF-8"' in html or 'charset="utf-8"' in html.lower(), (
        "index.html missing <meta charset='UTF-8'>"
    )
    assert "<title>" in html, "index.html missing <title> element"
    assert "ATLAS" in html, "index.html title must contain 'ATLAS'"


# ─── Test 2: All 10 required page links are present ─────────────────────────


def test_all_ten_required_page_links_present() -> None:
    """index.html must contain <a href> links to all 10 Stage-1 mockup pages."""
    html = _html()
    missing: list[str] = []
    for href in REQUIRED_HREFS:
        # Check for href="<page>" or href='<page>'
        pattern = f'href="{href}"'
        pattern_sq = f"href='{href}'"
        if pattern not in html and pattern_sq not in html:
            missing.append(href)
    assert not missing, f"index.html is missing links to: {missing}"


# ─── Test 3: Zero external links ─────────────────────────────────────────────


def test_zero_external_links() -> None:
    """index.html must contain no external links (no http:// or https:// hrefs)."""
    html = _html()
    # Find all href/src attributes
    href_pattern = re.compile(r'(?:href|src)=["\']([^"\']+)["\']', re.IGNORECASE)
    all_links = href_pattern.findall(html)
    external = [link for link in all_links if link.startswith(("http://", "https://", "//"))]
    assert not external, f"index.html contains {len(external)} external link(s): {external[:5]}"


# ─── Test 4: CSS token discipline — no raw colors ────────────────────────────


def test_no_raw_hex_colors_in_inline_styles() -> None:
    """Inline style attributes must not contain raw hex/rgb/hsl colors (fe-g-04)."""
    html = _html()
    inline_styles = re.findall(r'style="([^"]*)"', html)
    hex_pattern = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
    rgb_pattern = re.compile(r"rgb[a]?\s*\(")
    hsl_pattern = re.compile(r"hsl[a]?\s*\(")
    violations: list[str] = []
    for style in inline_styles:
        if hex_pattern.search(style) or rgb_pattern.search(style) or hsl_pattern.search(style):
            violations.append(style[:80])
    assert not violations, (
        "Inline styles contain raw color values (use CSS vars). Violations:\n"
        + "\n".join(violations[:5])
    )


# ─── Test 5: No dark mode residue ────────────────────────────────────────────


def test_no_dark_mode_residue() -> None:
    """index.html must not contain any dark mode patterns (fe-g-05)."""
    html = _html()
    dark_patterns = [
        "prefers-color-scheme: dark",
        'data-theme="dark"',
        'class="dark"',
        "--bg-dark",
        "--dark-",
    ]
    for pattern in dark_patterns:
        assert pattern not in html, f"index.html contains dark mode pattern: {pattern!r}"


# ─── Test 6: No verdict / LLM prose ─────────────────────────────────────────


def test_no_verdict_or_llm_prose() -> None:
    """index.html must not contain BUY/SELL/HOLD/verdict/LLM language (fe-g-06)."""
    html = _html()
    prohibited = [
        r"\bBUY\b",
        r"\bSELL\b",
        r"\bHOLD\b",
        r"\bRECOMMEND\b",
        r"Atlas Verdict",
        r"Atlas Insight",
        r"AI verdict",
        r"LLM says",
        r"GPT says",
    ]
    for pat in prohibited:
        match = re.search(pat, html, re.IGNORECASE)
        if match:
            context = html[max(0, match.start() - 40) : match.end() + 40]
            raise AssertionError(f"Prohibited pattern {pat!r} found. Context: ...{context}...")


# ─── Test 7: Indian i18n — no dollar or million/billion ─────────────────────


def test_indian_i18n_no_dollar_or_million_billion() -> None:
    """index.html must not use $ sign, million, or billion (fe-g-07)."""
    html = _html()
    # Check script and visible content (strip HTML tags for text check)
    text_content = re.sub(r"<[^>]+>", " ", html)
    assert "$" not in text_content, "index.html contains $ (must use ₹)"
    assert "million" not in text_content.lower(), (
        "index.html contains 'million' (must use lakh/crore)"
    )
    assert "billion" not in text_content.lower(), (
        "index.html contains 'billion' (must use lakh/crore)"
    )
