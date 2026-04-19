"""
V2FE E2E tests — Stock Detail (stock-detail.html) page.

Opens stock-detail.html via file:// and verifies:
1. Page loads without crash
2. [data-endpoint] blocks exist (binding contract)
3. Hero block resolves (data-block=hero or data-component=hero present)
4. page-level scope attr data-symbol present on <main>
5. atlas-data.js + atlas-states.js referenced

Notes:
- file:// protocol blocks XHR/fetch so data-state won't reach "ready"
- Tests verify DOM structure only
- SKIP if playwright is not installed or mockup missing
"""

from __future__ import annotations

from pathlib import Path

import pytest

MOCKUP_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "mockups"


def _open_page(page_name: str):  # type: ignore[return]
    """Skip if file doesn't exist."""
    html_path = MOCKUP_DIR / page_name
    if not html_path.exists():
        pytest.skip(f"Mockup file not found: {page_name}")
    return html_path


# ---------------------------------------------------------------------------
# stock-detail.html E2E
# ---------------------------------------------------------------------------


def test_stock_detail_page_loads(page) -> None:  # type: ignore[no-untyped-def]
    """stock-detail.html loads without crash."""
    html_path = _open_page("stock-detail.html")
    url = f"file://{html_path}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception as exc:
        pytest.fail(f"Failed to load stock-detail.html: {exc}")

    body = page.locator("body")
    assert body.count() > 0, "stock-detail.html: body not found"


def test_stock_detail_has_data_endpoint_blocks(page) -> None:  # type: ignore[no-untyped-def]
    """stock-detail.html must have ≥5 V2 binding blocks."""
    html_path = _open_page("stock-detail.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    selector = "[data-endpoint], [data-v2-derived], [data-v2-deferred], [data-v2-static]"
    blocks = page.locator(selector)
    count = blocks.count()
    assert count >= 5, f"stock-detail.html: expected ≥5 V2 binding blocks, got {count}"


def test_stock_detail_hero_block_present(page) -> None:  # type: ignore[no-untyped-def]
    """stock-detail.html must have a hero block (V2FE-5 exit criterion)."""
    html_path = _open_page("stock-detail.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    hero = page.locator("[data-block=hero], [data-component=hero], .hero-block, #hero")
    assert hero.count() >= 1, "stock-detail.html: hero block not found"


def test_stock_detail_main_has_symbol_scope(page) -> None:  # type: ignore[no-untyped-def]
    """stock-detail.html <main> must have data-symbol attr (page-level scope)."""
    html_path = _open_page("stock-detail.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    main_with_symbol = page.locator("main[data-symbol]")
    assert main_with_symbol.count() >= 1, (
        "stock-detail.html: <main data-symbol=...> not found (V2FE-5 page-level scope)"
    )


def test_stock_detail_atlas_data_js_referenced(page) -> None:  # type: ignore[no-untyped-def]
    """stock-detail.html must reference atlas-data.js and atlas-states.js."""
    html_path = _open_page("stock-detail.html")
    content = html_path.read_text(encoding="utf-8")
    assert "atlas-data.js" in content, "stock-detail.html: atlas-data.js not referenced"
    assert "atlas-states.js" in content, "stock-detail.html: atlas-states.js not referenced"
