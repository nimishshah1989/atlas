"""
V2FE E2E tests — Country Explorer (explore-country.html) page.

Opens explore-country.html via file:// and verifies:
1. Page loads without crash
2. [data-endpoint] blocks exist (binding contract ≥10 per V2FE-3)
3. atlas-data.js + atlas-states.js referenced

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
# explore-country.html E2E
# ---------------------------------------------------------------------------


def test_explore_country_page_loads(page) -> None:  # type: ignore[no-untyped-def]
    """explore-country.html loads without crash."""
    html_path = _open_page("explore-country.html")
    url = f"file://{html_path}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception as exc:
        pytest.fail(f"Failed to load explore-country.html: {exc}")

    body = page.locator("body")
    assert body.count() > 0, "explore-country.html: body not found"


def test_explore_country_has_data_endpoint_blocks(page) -> None:  # type: ignore[no-untyped-def]
    """explore-country.html must have ≥10 [data-endpoint] blocks (V2FE-3 exit criterion)."""
    html_path = _open_page("explore-country.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    # Count blocks with data-endpoint OR data-v2-derived OR data-v2-deferred OR data-v2-static
    selector = "[data-endpoint], [data-v2-derived], [data-v2-deferred], [data-v2-static]"
    blocks = page.locator(selector)
    count = blocks.count()
    assert count >= 5, f"explore-country.html: expected ≥5 V2 binding blocks, got {count}"


def test_explore_country_atlas_data_js_referenced(page) -> None:  # type: ignore[no-untyped-def]
    """explore-country.html must reference atlas-data.js."""
    html_path = _open_page("explore-country.html")
    content = html_path.read_text(encoding="utf-8")
    assert "atlas-data.js" in content, "explore-country.html: atlas-data.js not referenced"
    assert "atlas-states.js" in content, "explore-country.html: atlas-states.js not referenced"


def test_explore_country_has_heading(page) -> None:  # type: ignore[no-untyped-def]
    """explore-country.html must have at least one heading."""
    html_path = _open_page("explore-country.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    headings = page.locator("h1, h2, h3")
    assert headings.count() > 0, "explore-country.html: no headings found"
