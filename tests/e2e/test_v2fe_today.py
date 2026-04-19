"""
V2FE E2E tests — Pulse (today.html) page.

Opens today.html via file:// and verifies:
1. Page loads without crash
2. [data-endpoint] blocks exist (binding contract)
3. [data-role=sector-board] element is present
4. No data-v2-static blocks are missing

Notes:
- file:// protocol blocks XHR/fetch so data-state won't reach "ready"
- Tests verify DOM structure (binding contract), not live data
- SKIP if playwright is not installed
"""

from __future__ import annotations

from pathlib import Path

import pytest

MOCKUP_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "mockups"


def _get_page_fixture():
    """Return a playwright page, or skip if playwright unavailable."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")
    return sync_playwright


def _open_page(page_name: str):  # type: ignore[return]
    """Skip if file doesn't exist."""
    html_path = MOCKUP_DIR / page_name
    if not html_path.exists():
        pytest.skip(f"Mockup file not found: {page_name}")
    return html_path


# ---------------------------------------------------------------------------
# today.html E2E
# ---------------------------------------------------------------------------


def test_today_page_loads(page) -> None:  # type: ignore[no-untyped-def]
    """today.html loads without crash."""
    html_path = _open_page("today.html")
    url = f"file://{html_path}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception as exc:
        pytest.fail(f"Failed to load today.html: {exc}")

    body = page.locator("body")
    assert body.count() > 0, "today.html: body not found"


def test_today_has_data_endpoint_blocks(page) -> None:  # type: ignore[no-untyped-def]
    """today.html must have at least one [data-endpoint] block (V2 binding contract)."""
    html_path = _open_page("today.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    blocks = page.locator("[data-endpoint]")
    count = blocks.count()
    assert count >= 1, f"today.html: expected ≥1 [data-endpoint] blocks, got {count}"


def test_today_has_sector_board(page) -> None:  # type: ignore[no-untyped-def]
    """today.html must have [data-role=sector-board] element."""
    html_path = _open_page("today.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    board = page.locator("[data-role=sector-board], [data-block=sector-board]")
    assert board.count() >= 1, "today.html: [data-role=sector-board] not found"


def test_today_atlas_data_js_referenced(page) -> None:  # type: ignore[no-untyped-def]
    """today.html must reference atlas-data.js script (V2 loader contract)."""
    html_path = _open_page("today.html")
    content = html_path.read_text(encoding="utf-8")
    assert "atlas-data.js" in content, "today.html: atlas-data.js not referenced"
    assert "atlas-states.js" in content, "today.html: atlas-states.js not referenced"
