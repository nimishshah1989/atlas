"""
V2FE E2E tests — Breadth Terminal (breadth.html) page.

Opens breadth.html via file:// and verifies:
1. Page loads without crash
2. [data-endpoint] blocks exist
3. [data-block=signal-history] block is present (V2FE-4 exit criterion)
4. atlas-data.js + atlas-states.js referenced

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
# breadth.html E2E
# ---------------------------------------------------------------------------


def test_breadth_page_loads(page) -> None:  # type: ignore[no-untyped-def]
    """breadth.html loads without crash."""
    html_path = _open_page("breadth.html")
    url = f"file://{html_path}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception as exc:
        pytest.fail(f"Failed to load breadth.html: {exc}")

    body = page.locator("body")
    assert body.count() > 0, "breadth.html: body not found"


def test_breadth_has_data_endpoint_blocks(page) -> None:  # type: ignore[no-untyped-def]
    """breadth.html must have ≥5 V2 binding blocks."""
    html_path = _open_page("breadth.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    selector = "[data-endpoint], [data-v2-derived], [data-v2-deferred], [data-v2-static]"
    blocks = page.locator(selector)
    count = blocks.count()
    assert count >= 5, f"breadth.html: expected ≥5 V2 binding blocks, got {count}"


def test_breadth_signal_history_block_present(page) -> None:  # type: ignore[no-untyped-def]
    """breadth.html must have [data-block=signal-history] (V2FE-4 exit criterion)."""
    html_path = _open_page("breadth.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    block = page.locator("[data-block=signal-history]")
    assert block.count() >= 1, "breadth.html: [data-block=signal-history] not found"


def test_breadth_atlas_data_js_referenced(page) -> None:  # type: ignore[no-untyped-def]
    """breadth.html must reference atlas-data.js and atlas-states.js."""
    html_path = _open_page("breadth.html")
    content = html_path.read_text(encoding="utf-8")
    assert "atlas-data.js" in content, "breadth.html: atlas-data.js not referenced"
    assert "atlas-states.js" in content, "breadth.html: atlas-states.js not referenced"
